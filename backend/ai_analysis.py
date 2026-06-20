# ai_analysis.py
import os
import json
import time
import base64
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY is missing from your .env file")

client = genai.Client(api_key=GEMINI_API_KEY)

UNRELATED_RECOMMENDATION_MESSAGE = "Sorry, I cannot help you with that"

_SHOPPING_GUARD_TERMS = {
    "amazon", "ebay", "buy", "deal", "deals", "price", "prices", "cheap", "budget",
    "discount", "discounts", "sale", "sales", "coupon", "coupons", "clearance",
    "markdown", "savings", "save", "promo", "promotion",
    "expensive", "affordable", "recommend", "recommendation", "alternative", "compare",
    "similar", "brand", "product", "products", "quality", "durable", "durability",
    "rating", "reviews", "under", "over", "headphones", "earbuds", "speaker", "laptop", "laptops",
    "airpods", "apple", "sony", "bose", "jbl", "anker", "soundcore", "samsung",
    "keyboard", "keyboards", "mouse", "mice", "monitor", "monitors", "camera", "cameras",
    "charger", "chargers", "case", "cases", "watch", "watches", "phone", "phones",
    "tablet", "tablets", "vacuum", "vacuums", "air fryer", "coffee", "backpack", "backpacks", "bottle", "best",
    "popular", "current", "top", "avoid", "water", "shoes", "boots", "shirt",
    "clothing", "skincare", "cleanser", "bottles", "students", "school", "college",
    "work", "gaming", "portable", "budget", "reviews",
}

_PRODUCT_DISCOVERY_RE = re.compile(
    r"\b(find|search|show|shop|get|recommend|recommendations?|best|top|popular|current|"
    r"under|below|cheaper|budget|alternatives?|similar\s+to|compare\s+options?)\b",
    re.IGNORECASE,
)
_BRAND_AVOIDANCE_RE = re.compile(r"\b(brands?\s+to\s+avoid|avoid\s+brands?|what\s+brands?\s+should\s+i\s+avoid)\b", re.IGNORECASE)


def _shopping_word_forms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", str(text or "").lower()))
    singularized = {
        word[:-1]
        for word in words
        if len(word) > 3 and word.endswith("s")
    }
    return words | singularized


def _looks_like_product_discovery_request(text: str) -> bool:
    text = str(text or "").strip()
    if not text:
        return False
    if _BRAND_AVOIDANCE_RE.search(text):
        return False
    words = _shopping_word_forms(text)
    return bool(_PRODUCT_DISCOVERY_RE.search(text)) and bool(words & _SHOPPING_GUARD_TERMS)


def _compact_scan_memory(history: list[dict], limit: int = 8) -> list[dict]:
    memory = []
    for index, item in enumerate(history[:limit]):
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue
        review_integrity = analysis.get("reviewIntegrity") or {}
        seller_integrity = analysis.get("sellerReviewIntegrity") or {}
        brand_reputation = analysis.get("brandReputation") or {}
        review_keywords = review_integrity.get("commonKeywords", []) if isinstance(review_integrity, dict) else []
        seller_keywords = seller_integrity.get("commonKeywords", []) if isinstance(seller_integrity, dict) else []
        brand_keywords = brand_reputation.get("commonKeywords", []) if isinstance(brand_reputation, dict) else []
        similar_products = analysis.get("similarProducts") or []
        memory.append({
            "recencyRank": index + 1,
            "scannedAt": item.get("scannedAt"),
            "url": item.get("url"),
            "title": analysis.get("title"),
            "brand": analysis.get("brand"),
            "productKeyword": analysis.get("productKeyword"),
            "price": analysis.get("price"),
            "rating": analysis.get("rating"),
            "reviewCount": analysis.get("reviewCount"),
            "overallScore": analysis.get("overallScore"),
            "marketplace": analysis.get("marketplace"),
            "aiVerdict": (analysis.get("aiAnalysis") or {}).get("verdict") if isinstance(analysis.get("aiAnalysis"), dict) else "",
            "positiveSignals": [
                keyword.get("word")
                for keyword in (review_keywords + seller_keywords + brand_keywords)
                if isinstance(keyword, dict) and keyword.get("sentiment") == "positive"
            ][:8],
            "negativeSignals": [
                keyword.get("word")
                for keyword in (review_keywords + seller_keywords + brand_keywords)
                if isinstance(keyword, dict) and keyword.get("sentiment") == "negative"
            ][:8],
            "nearbyAlternatives": [
                {
                    "title": product.get("title"),
                    "brand": product.get("brand"),
                    "price": product.get("price"),
                    "rating": product.get("rating"),
                    "reviewCount": product.get("reviewCount"),
                    "marketplace": product.get("marketplace"),
                }
                for product in similar_products[:4]
                if isinstance(product, dict)
            ],
        })
    return memory


def _looks_like_shopping_prompt(prompt: str, recent_items: list[dict]) -> bool:
    if not prompt:
        return True

    if _looks_like_product_discovery_request(prompt) or _BRAND_AVOIDANCE_RE.search(prompt):
        return True

    words = _shopping_word_forms(prompt)
    if words & _SHOPPING_GUARD_TERMS:
        return True

    recent_text = " ".join(
        str(item.get(key) or "")
        for item in recent_items
        for key in ("title", "brand", "productKeyword")
    ).lower()
    return any(word and len(word) >= 4 and word in recent_text for word in words)


def build_recommendation_query(
    history: list[dict],
    filter_mode: str = "overall",
    refinement_prompt: str = "",
    image_data_url: str = "",
) -> dict:
    """Use Gemini to turn scan memory and user refinements into a commerce search."""
    filter_mode = filter_mode if filter_mode in ("overall", "durability", "price", "quality") else "overall"
    refinement_prompt = (refinement_prompt or "").strip()

    recent_items = _compact_scan_memory(history, 8)

    fallback_term = "popular products"
    for item in recent_items:
        fallback_term = (
            item.get("productKeyword")
            or item.get("title")
            or fallback_term
        )
        if fallback_term and fallback_term != "unknown":
            break

    suffix_by_filter = {
        "overall": "best value",
        "durability": "durable reliable",
        "price": "budget affordable deal",
        "quality": "top rated premium",
    }

    def fallback_search_terms(base: str) -> list[str]:
        base = re.sub(r"\s+", " ", str(base or "").strip())
        if not base:
            base = fallback_term
        suffix = suffix_by_filter[filter_mode]
        terms = [base]
        if suffix and suffix not in base.lower():
            terms.append(f"{base} {suffix}".strip())
        if re.search(r"\blaptops?\b|\bchromebooks?\b|\bnotebooks?\b", base, re.IGNORECASE):
            terms.extend([
                "student laptop durable affordable",
                "best rated laptop for students",
                "budget laptop 16gb ram ssd",
            ])
        elif re.search(r"\bwater bottles?\b|\btumbler\b|\bbottle\b", base, re.IGNORECASE):
            terms.extend([
                "insulated water bottle leakproof",
                "top rated water bottle under 50",
                "durable stainless steel water bottle",
            ])
        elif re.search(r"\bheadphones?\b|\bearbuds?\b|\bairpods?\b", base, re.IGNORECASE):
            terms.extend([
                "top rated wireless headphones",
                "best value noise cancelling headphones",
                "wireless earbuds strong reviews",
            ])
        cleaned: list[str] = []
        for term in terms:
            term = re.sub(r"\s+", " ", term).strip()
            if term and term.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(term[:120])
        return cleaned[:5]

    prompt = f"""You are Nectar's smart shopping recommender.

Return JSON only.

User scan memory:
{json.dumps(recent_items, ensure_ascii=False)}

Current filter: {filter_mode}
User refinement: {refinement_prompt or "none"}

Task:
- First decide if the user request is in scope.
- In scope means finding, refining, comparing, or recommending purchasable products using scan memory, filter, prompt, or uploaded product photo.
- Out of scope includes general Q&A, coding, homework, jokes, politics, medical/legal/financial advice, recipes, weather, personal questions, or anything not about product recommendations.
- If out of scope, return allowed=false, query="", reason="{UNRELATED_RECOMMENDATION_MESSAGE}".
- Never answer the user's unrelated question.
- Infer what product category the user is currently interested in.
- Act as a recommendation orchestrator over the user's behavior, not a generic search box.
- Put the most weight on recencyRank 1-3, then use older scans as secondary preference evidence.
- Favor product categories, features, price tiers, quality signals, and marketplaces that repeat in recent history.
- Use nearbyAlternatives as evidence of what the user has already been shown; search for directly connected products without simply repeating the exact same listing.
- If a photo is included, use its visible product style/brand/category as a refinement.
- Create one concise primary marketplace query and 3 to 5 searchTerms that should return 5 products the user would like.
- searchTerms should be varied but category-locked: include the user's exact category, then useful alternates with budget, quality, durability, rating, or feature words.
- Do not put unrelated scan-history categories into searchTerms when the user asks for a specific product category.
- Prefer cross-brand alternatives by default. Do not include a brand from scan memory in the query unless the user explicitly asks for that brand or same-brand products.
- If the user asks for a specific brand, honor it.
- Tune the query for the filter:
  overall = balanced value, reviews, trust
  durability = reliable, long-lasting, sturdy, reputable
  price = budget, deal, affordable, best value
  quality = premium, top rated, high quality
- Prefer concrete categories like "noise cancelling headphones" over vague terms.

Schema:
{{"allowed":true,"query":"string","searchTerms":["string"],"reason":"string"}}
"""

    schema = {
        "type": "object",
        "properties": {
            "allowed": {"type": "boolean"},
            "query": {"type": "string"},
            "searchTerms": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["allowed", "query", "searchTerms", "reason"],
    }

    try:
        contents: list = [prompt]
        if image_data_url:
            match = re.match(r"^data:(image/[^;]+);base64,(.+)$", image_data_url)
            if match:
                mime_type, raw_data = match.groups()
                contents.append(types.Part.from_bytes(
                    data=base64.b64decode(raw_data),
                    mime_type=mime_type,
                ))

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.35,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )

        result = json.loads((response.text or "").strip())
        if result.get("allowed") is False:
            if image_data_url or _looks_like_shopping_prompt(refinement_prompt, recent_items):
                fallback_query = refinement_prompt or fallback_term
                return {
                    "query": fallback_query[:120],
                    "searchTerms": fallback_search_terms(fallback_query),
                    "reason": "Using the product request directly.",
                }
            return {
                "rejected": True,
                "message": UNRELATED_RECOMMENDATION_MESSAGE,
                "query": "",
                "reason": UNRELATED_RECOMMENDATION_MESSAGE,
            }

        query = str(result.get("query") or "").strip()
        if not query:
            query = fallback_term
        search_terms = [
            str(term or "").strip()[:120]
            for term in (result.get("searchTerms") or [])
            if str(term or "").strip()
        ]
        if not search_terms:
            search_terms = fallback_search_terms(query)
        return {
            "query": query[:120],
            "searchTerms": search_terms[:5],
            "reason": str(result.get("reason") or "Based on recent scan history.").strip()[:220],
        }
    except Exception as e:
        print(f"[Recommendations] Gemini query build failed: {e}")
        if image_data_url and not refinement_prompt:
            return {
                "rejected": True,
                "message": "Could not identify the uploaded product. Try adding a short prompt.",
                "query": "",
                "reason": "Image refinement could not be processed.",
            }
        prompt_term = refinement_prompt if refinement_prompt else fallback_term
        return {
            "query": str(prompt_term).strip()[:120],
            "searchTerms": fallback_search_terms(prompt_term),
            "reason": "Using the product request and selected filter.",
        }


def build_price_trend_narrative(
    analysis: dict,
    points: list[dict],
    insights: list[dict],
) -> dict:
    """Use Gemini to summarize a price trajectory and drop likelihood."""
    title = analysis.get("title") or "this product"
    prompt = f"""You are Nectar's price intelligence analyst.

Return JSON only.

Product:
{json.dumps({
    "title": title,
    "brand": analysis.get("brand"),
    "price": analysis.get("price"),
    "rating": analysis.get("rating"),
    "reviewCount": analysis.get("reviewCount"),
    "overallScore": analysis.get("overallScore"),
    "marketplace": analysis.get("marketplace"),
}, ensure_ascii=False)}

Price series:
{json.dumps(points, ensure_ascii=False)}

Computed insights:
{json.dumps(insights, ensure_ascii=False)}

Task:
- Write a concise trajectory narrative grounded in the series.
- Make a likelyToDrop call: true only when the recent movement, volatility, or current premium suggests waiting could pay off.
- Give confidence from 0 to 1.
- Include 2 to 4 short chart callouts users can scan.

Schema:
{{"narrative":"string","likelyToDrop":true,"confidence":0.0,"callouts":["string"]}}
"""

    schema = {
        "type": "object",
        "properties": {
            "narrative": {"type": "string"},
            "likelyToDrop": {"type": "boolean"},
            "confidence": {"type": "number"},
            "callouts": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["narrative", "likelyToDrop", "confidence", "callouts"],
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.35,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        result = json.loads((response.text or "").strip())
        return {
            "narrative": str(result.get("narrative") or "").strip()[:900],
            "likelyToDrop": bool(result.get("likelyToDrop")),
            "confidence": max(0.0, min(1.0, float(result.get("confidence") or 0.0))),
            "callouts": [
                str(callout).strip()[:120]
                for callout in (result.get("callouts") or [])
                if str(callout).strip()
            ][:4],
        }
    except Exception as e:
        print(f"[Price Trend] Gemini trend narrative failed: {e}")
        if len(points) >= 2:
            first = points[0].get("price")
            last = points[-1].get("price")
            delta = (last or 0) - (first or 0)
        else:
            delta = 0
        likely = delta > 0
        return {
            "narrative": (
                "Recent pricing is estimated from the current listing and product context. "
                f"The trajectory is {'above its starting point' if delta > 0 else 'stable to slightly softer'}, "
                "so use this as a directional signal rather than live marketplace history."
            ),
            "likelyToDrop": likely,
            "confidence": 0.56 if likely else 0.48,
            "callouts": [str(item.get("label") or "") for item in insights if item.get("label")][:4],
        }


def get_ai_verdict(
    title: str,
    reviews: list,
    overall_score: int,
    integrity_score: int,
    reputation_score: int,
    marketplace: str = "amazon",
    seller_positive_pct=None,
    delivery_min=None,
    delivery_max=None,
    return_policy=None,
    condition=None,
    price=None,
    product_keyword=None,
):

    review_snippets = "\n".join(
        f"- [{r.get('rating', '?')}★] {r.get('body', '')[:200]}"
        for r in reviews[:15]
        if r.get("body", "").strip()
    )

    print(f"[AI Analysis] reviews received: {len(reviews)}")
    print(f"[AI Analysis] snippets built: {len(review_snippets.splitlines())}")

    metadata_summary = []

    if seller_positive_pct is not None:
        metadata_summary.append(f"Seller feedback: {seller_positive_pct}% positive")

    if delivery_min and delivery_max:
        metadata_summary.append(f"Delivery estimate: {delivery_min}–{delivery_max}")

    if return_policy:
        metadata_summary.append(f"Returns: {return_policy}")

    if condition:
        metadata_summary.append(f"Condition: {condition}")

    clean_metadata_summary = []
    if product_keyword and product_keyword != "unknown":
        clean_metadata_summary.append(f"Product category: {product_keyword}")
    if price:
        clean_metadata_summary.append(f"Price: {_clean_metadata_value(price)}")
    if seller_positive_pct is not None:
        clean_metadata_summary.append(f"Seller feedback: {seller_positive_pct}% positive")

    min_text = _clean_metadata_value(delivery_min)
    max_text = _clean_metadata_value(delivery_max)
    if min_text and max_text:
        clean_metadata_summary.append(f"Delivery estimate: {min_text} to {max_text}")
    elif min_text or max_text:
        clean_metadata_summary.append(f"Delivery estimate: {min_text or max_text}")
    if return_policy:
        clean_metadata_summary.append(f"Returns: {_clean_metadata_value(return_policy)}")
    if condition:
        clean_metadata_summary.append(f"Condition: {_clean_metadata_value(condition)}")
    metadata_summary = clean_metadata_summary

    metadata_text = "\n".join(metadata_summary)

    is_ebay = marketplace == "ebay"
    platform_name = "eBay" if is_ebay else "Amazon"
    review_type = "eBay seller reviews" if is_ebay else "Amazon product reviews"
    integrity_title = "Seller Review Integrity" if is_ebay else "Review Integrity"
    reputation_title = "Seller Reputation" if is_ebay else "Brand Reputation"

    prompt = f"""You are a shopping assistant analyzing {platform_name} product reviews.

Product: {title}
Trust Score: {overall_score}/100
{integrity_title}: {integrity_score}/100
{reputation_title}: {reputation_score}/100

Metadata:
{metadata_text or "N/A"}

Customer reviews:
{review_snippets}

Return JSON only.

Rules:
- pros/cons must come directly from patterns in the reviews, not invented
- verdict must be one sentence, max 24 words
- verdict must name or clearly describe the specific product/category, not just the resale listing
- include product-specific context from the title or metadata when it is relevant
- recommendation: BUY if score>=75, SKIP if score<50, otherwise COMPARE
- if reviews are overwhelmingly positive with no real cons, make the cons minor nitpicks only
"""

    schema = {
        "type": "object",
        "properties": {
            "pros": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "cons": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "verdict": {"type": "string"},
            "recommendation": {
                "type": "string",
                "enum": ["BUY", "COMPARE", "SKIP"],
            },
        },
        "required": ["pros", "cons", "verdict", "recommendation"],
    }

    try:
        print("[AI Analysis] Calling Gemini...")

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]

        for model_name in models_to_try:
            for attempt in range(3):
                try:
                    print(f"[AI Analysis] Trying {model_name} (attempt {attempt + 1})")

                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            response_mime_type="application/json",
                            response_json_schema=schema,
                        ),
                    )

                    raw = (response.text or "").strip()
                    print(f"[AI Analysis] ✅ Gemini responded: {raw[:300]}")

                    result = json.loads(raw)

                    pros = result.get("pros", [])
                    cons = result.get("cons", [])

                    while len(pros) < 3:
                        pros.append("No further pros identified")
                    while len(cons) < 3:
                        cons.append("No further cons identified")

                    rec = result.get("recommendation", "COMPARE")
                    if rec not in ("BUY", "COMPARE", "SKIP"):
                        rec = "COMPARE"

                    return {
                        "pros": pros[:3],
                        "cons": cons[:3],
                        "verdict": result.get("verdict", _fallback_verdict(title, overall_score, marketplace)),
                        "recommendation": rec,
                    }

                except Exception as e:
                    if _is_quota_exhausted(e):
                        print(f"[AI Analysis] Quota exhausted for {model_name}; using fallback verdict.")
                        return _fallback(overall_score, marketplace=marketplace)

                    print(f"[AI Analysis] ⚠️ {model_name} failed: {e}")
                    time.sleep(1.5 * (attempt + 1))

        print("[AI Analysis] ❌ All Gemini attempts failed")
        return _fallback(overall_score, marketplace=marketplace)

    except Exception as e:
        print(f"[AI Analysis] ❌ FINAL EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return _fallback(overall_score, marketplace=marketplace)


def _fallback_verdict(title: str, overall_score: int, marketplace: str = "amazon") -> str:
    product_name = re.sub(r"\s+", " ", title or "This product").strip()
    if len(product_name) > 72:
        product_name = product_name[:69].rstrip() + "..."
    if marketplace == "ebay":
        return f"{product_name} depends on seller trust, condition, returns, and fit for the buyer."
    if overall_score >= 75:
        return f"{product_name} looks strong based on the available trust signals."
    if overall_score < 50:
        return f"{product_name} shows enough trust concerns to compare alternatives first."
    return f"{product_name} is worth comparing against similar options before buying."


def _fallback(overall_score: int, marketplace: str = "amazon") -> dict:
    is_ebay = marketplace == "ebay"
    rec = "BUY" if overall_score >= 75 else "SKIP" if overall_score < 50 else "COMPARE"
    return {
        "pros": [
            "Verified purchase ratio is strong",
            "Rating aligns with review sentiment",
            "Seller has positive reputation" if is_ebay else "Brand has positive reputation",
        ],
        "cons": [
            "Limited review data available",
            "Could not extract detailed feedback",
            "Manual review recommended",
        ],
        "verdict": "Analysis is based on trust signals because detailed review text is limited.",
        "recommendation": rec,
    }


def explain_score_with_ai(metric_name: str, analysis: dict) -> dict:
    title = analysis.get("title") or "Unknown product"
    overall_score = analysis.get("overallScore")
    marketplace = analysis.get("marketplace", "amazon")
    is_ebay = marketplace == "ebay"

    review_integrity = analysis.get("reviewIntegrity") or analysis.get("sellerReviewIntegrity") or {}
    brand_reputation = analysis.get("brandReputation") or analysis.get("sellerReputation") or {}
    raw = analysis.get("raw") or {}
    reviews = raw.get("reviews") or []

    review_snippets = "\n".join(
        f"- [{r.get('rating', '?')}★] {(r.get('body') or '')[:180]}"
        for r in reviews[:8]
        if (r.get("body") or "").strip()
    )

    if metric_name in ("review_integrity", "seller_review_integrity"):
        metric_title = "Seller Review Integrity" if is_ebay else "Review Integrity"
        score = review_integrity.get("score")
        details = {
            "label": review_integrity.get("label"),
            "verified_purchase_ratio": review_integrity.get("verifiedPurchaseRatio"),
            "sentiment_consistency_ratio": review_integrity.get("sentimentConsistencyRatio"),
            "flags": review_integrity.get("flags", {}),
            "common_keywords": review_integrity.get("commonKeywords", []),
        }
        instructions = "Focus on verified purchase ratio, sentiment consistency, suspicious patterns, and review keyword trends."
    elif metric_name in ("brand_reputation", "seller_reputation"):
        metric_title = "Seller Reputation" if is_ebay else "Brand Reputation"
        score = brand_reputation.get("score")
        details = {
            "label": brand_reputation.get("label"),
            "reviews_analyzed": brand_reputation.get("reviewsAnalyzed"),
            "insights": brand_reputation.get("insights", []),
            "common_keywords": brand_reputation.get("commonKeywords", []),
        }
        if is_ebay:
            details["sellerName"] = brand_reputation.get("sellerName")
            details["sellerPositivePct"] = brand_reputation.get("sellerPositivePct")
            details["sellerReviewCount"] = brand_reputation.get("sellerReviewCount")
            details["topRatedSeller"] = brand_reputation.get("topRatedSeller")
        instructions = "Focus on Trustpilot-style seller sentiment, the insight categories, and recurring positive or negative themes in the seller keywords." if is_ebay else "Focus on Trustpilot-style brand sentiment, the insight categories, and recurring positive or negative themes in the brand keywords."
    else:
        return {"answer": "Unknown score type."}

    prompt = f"""You are explaining a product analysis score to a shopper.

Product: {title}
Overall Score: {overall_score}/100
Metric: {metric_title}
Metric Score: {score}/100

Metric details:
{json.dumps(details, indent=2)}

{"eBay seller review snippets" if is_ebay else "Amazon review snippets"} (if available):
{review_snippets or 'No review snippets available.'}

Instructions:
- Explain why this score has this value in 3 to 5 short sentences
- Use only the provided evidence
- Mention the biggest drivers of the score
- Do not invent facts
- Keep the tone clear and shopper-friendly
- End with one brief takeaway sentence
- {instructions}

Return JSON only in this exact shape:
{{
  "answer": "string"
}}
"""

    schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
        },
        "required": ["answer"],
    }

    try:
        print(f"[AI Explain] Calling Gemini for {metric_name}...")

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]

        for model_name in models_to_try:
            for attempt in range(3):
                try:
                    print(f"[AI Explain] Trying {model_name} (attempt {attempt + 1})")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.2,
                            response_mime_type="application/json",
                            response_json_schema=schema,
                        ),
                    )

                    raw_text = (response.text or "").strip()
                    print(f"[AI Explain] ✅ Gemini responded: {raw_text[:300]}")
                    result = json.loads(raw_text)
                    answer = (result.get("answer") or "").strip()
                    if answer:
                        return {"answer": answer}
                except Exception as e:
                    if _is_quota_exhausted(e):
                        print(f"[AI Explain] Quota exhausted for {model_name}; using fallback explanation.")
                        return {"answer": _score_explainer_fallback(metric_name, analysis)}

                    print(f"[AI Explain] ⚠️ {model_name} failed: {e}")
                    time.sleep(1.5 * (attempt + 1))

        return {"answer": _score_explainer_fallback(metric_name, analysis)}

    except Exception as e:
        print(f"[AI Explain] ❌ FINAL EXCEPTION: {e}")
        return {"answer": _score_explainer_fallback(metric_name, analysis)}


def _score_explainer_fallback(metric_name: str, analysis: dict) -> str:
    marketplace = analysis.get("marketplace", "amazon")
    is_ebay = marketplace == "ebay"
    if metric_name in ("review_integrity", "seller_review_integrity"):
        ri = analysis.get("reviewIntegrity") or analysis.get("sellerReviewIntegrity") or {}
        score = ri.get("score", "N/A")
        verified = ri.get("verifiedPurchaseRatio", "N/A")
        consistency = ri.get("sentimentConsistencyRatio", "N/A")
        flags = ", ".join((ri.get("flags") or {}).keys()) or "none"
        if is_ebay:
            return (
                f"The seller review integrity score is {score} because it mainly depends on verified purchase ratio "
                f"({verified}) and sentiment consistency ({consistency}). "
                f"The current label reflects how often written review tone matches the star ratings. "
                f"Detected warning flags: {flags}."
            )
        else:
            return (
                f"The review integrity score is {score} because it mainly depends on verified purchase ratio "
                f"({verified}) and sentiment consistency ({consistency}). "
                f"The current label reflects how often written review tone matches the star ratings. "
                f"Detected warning flags: {flags}."
            )

    br = analysis.get("brandReputation") or analysis.get("sellerReputation") or {}
    score = br.get("score", "N/A")
    reviews_analyzed = br.get("reviewsAnalyzed", "N/A")
    insight_bits = []
    for insight in (br.get("insights") or [])[:3]:
        topic = insight.get("topic")
        status = insight.get("status")
        if topic and status:
            insight_bits.append(f"{topic}: {status}")
    insight_text = "; ".join(insight_bits) or "limited insight data available"
    if is_ebay:
        seller_name = br.get("sellerName") or "the seller"
        return (
            f"The seller reputation score is {score} based on external seller sentiment signals across {reviews_analyzed} reviews for {seller_name}. "
            f"The strongest drivers shown here are {insight_text}. "
            f"The label summarizes whether the broader seller feedback looks strong, mixed, or weak overall."
        )
    else:
        return (
            f"The brand reputation score is {score} based on external brand sentiment signals across {reviews_analyzed} reviews. "
            f"The strongest drivers shown here are {insight_text}. "
            f"The label summarizes whether the broader brand feedback looks strong, mixed, or weak overall."
        )
