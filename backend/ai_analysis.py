# ai_analysis.py
import os
import json
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY is missing from your .env file")

client = genai.Client(api_key=GEMINI_API_KEY)


def _is_quota_exhausted(error: Exception) -> bool:
    message = str(error).upper()
    return "RESOURCE_EXHAUSTED" in message or "429" in message or "QUOTA" in message


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
- verdict must be one sentence, max 20 words
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
                        "verdict": result.get("verdict", "See scores above."),
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
        "verdict": "Analysis based on scores only — not enough review text available.",
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
