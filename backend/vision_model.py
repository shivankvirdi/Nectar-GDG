import re
from urllib.parse import unquote, urlparse
from .ai_analysis import get_ai_verdict

from .brand_reputation import get_brand_reputation
from .canopy_client import get_full_product_profile, search_similar_products
from .review_integrity import analyze_review_integrity

PRODUCT_KEYWORDS = [
    "screen protector",
    "phone case",
    "case",
    "charger",
    "charging cable",
    "cable",
    "wireless charger",
    "power bank",
    "laptop",
    "smartphone",
    "wired earbuds",
    "wireless earbuds",
    "headphones",
    "monitor",
    "television",
    "speaker",
    "tablet",
    "computer mouse",
    "camera",
    "keyboard",
    "printer",
    "gaming console",
    "router",
    "microphone",
    "watch",
]


def normalize_url_text(url: str) -> str:
    parsed = urlparse(url)
    raw_text = f"{parsed.netloc} {parsed.path} {parsed.query}"
    decoded = unquote(raw_text).lower()
    return re.sub(r"[-_/+=%]+", " ", decoded)


def extract_product_keyword(url: str) -> str:
    normalized = normalize_url_text(url)

    for keyword in sorted(PRODUCT_KEYWORDS, key=len, reverse=True):
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, normalized):
            return keyword

    return "unknown"


def extract_asin(url: str) -> str | None:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def build_overall_score(product_rating: float | int | None, integrity_score: int, reputation_score: int) -> int:
    rating_component = 0
    if product_rating is not None:
        rating_component = round((float(product_rating) / 5) * 100)

    return round((rating_component * 0.4) + (integrity_score * 0.35) + (reputation_score * 0.25))


def detect_accessory_type(title: str, fallback_keyword: str) -> str:
    text = (title or "").lower()

    if "screen protector" in text or "tempered glass" in text:
        return "screen protector"
    if "phone case" in text or re.search(r"\bcase\b", text):
        return "phone case"
    if "charger" in text:
        return "charger"
    if "wireless charger" in text:
        return "wireless charger"
    if "cable" in text:
        return "charging cable"
    if "power bank" in text:
        return "power bank"

    return fallback_keyword if fallback_keyword != "unknown" else ""


def extract_device_name(title: str) -> str:
    text = (title or "").strip()

    patterns = [
        r"(iPhone\s+\d+(?:\s*(?:Pro Max|Pro|Plus|Mini))?)",
        r"(Samsung\s+Galaxy\s+[A-Z0-9+\- ]+)",
        r"(Galaxy\s+S\d+(?:\s*(?:Plus|Ultra|FE))?)",
        r"(Galaxy\s+Z\s+(?:Fold|Flip)\s*\d*)",
        r"(iPad\s+[A-Za-z0-9\s]+)",
        r"(MacBook\s+(?:Air|Pro)\s+\d+(?:-inch)?)",
        r"(Pixel\s+\d+(?:\s*(?:Pro|a|XL))?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def clean_similar_products(similar_products: list, original_asin: str) -> list:
    cleaned = []
    seen_asins = set()

    for item in similar_products:
        if not isinstance(item, dict):
            continue

        asin = item.get("asin")
        title = (item.get("title") or "").strip()

        if not asin or asin == original_asin:
            continue

        if asin in seen_asins:
            continue

        if not title:
            continue

        seen_asins.add(asin)
        cleaned.append(item)

    return cleaned


def build_similar_search_terms(title: str, brand_name: str, product_keyword: str) -> list[str]:
    title = (title or "").strip()
    brand_name = (brand_name or "").strip()
    accessory_type = detect_accessory_type(title, product_keyword)
    device_name = extract_device_name(title)

    search_terms = []

    if device_name and accessory_type:
        if accessory_type == "screen protector":
            search_terms.append(f"{device_name} tempered glass {accessory_type}")
            search_terms.append(f"{device_name} {accessory_type}")
        else:
            search_terms.append(f"{device_name} {accessory_type}")

    if brand_name and accessory_type:
        search_terms.append(f"{brand_name} {accessory_type}")

    if accessory_type:
        search_terms.append(accessory_type)

    if title:
        search_terms.append(title)

    deduped = []
    seen = set()
    for term in search_terms:
        normalized = term.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(term)

    return deduped


async def analyze_product_url(url: str) -> dict:
    asin = extract_asin(url)
    if not asin:
        raise ValueError("Could not find an Amazon ASIN in the provided URL.")

    product_keyword = extract_product_keyword(url)
    profile = get_full_product_profile(asin)

    product = profile.get("product", {})
    brand = profile.get("brand", "") or product.get("brand", "")

    reviews = profile.get("reviews") or []
    review_integrity = analyze_review_integrity(reviews)

    brand_reputation = await get_brand_reputation(brand, reviews) if brand else {
        "brand": "",
        "reputation_score_pct": None,
        "overall_label": "Brand not found.",
        "insights": [],
        "reviews_analyzed": 0,
        "commonKeywords": [],
    }

    similar_products = []

    title = (product.get("title") or "").strip()
    brand_name = (brand or "").strip()

    search_terms = build_similar_search_terms(title, brand_name, product_keyword)

    for term in search_terms:
        results = search_similar_products(term)
        if results:
            similar_products = results
            break

    similar_products = clean_similar_products(similar_products, asin)

    rating = product.get("rating")
    integrity_score = review_integrity.get("integrity_score_pct", 50)
    reputation_score = brand_reputation.get("reputation_score_pct") or 50

    overall_score = build_overall_score(rating, integrity_score, reputation_score)

    ai_analysis = get_ai_verdict(
        title=title,
        reviews=reviews,
        overall_score=overall_score,
        integrity_score=integrity_score,
        reputation_score=reputation_score,
    )

    return {
        "asin": asin,
        "productKeyword": product_keyword,
        "title": product.get("title"),
        "brand": brand,
        "price": (product.get("price") or {}).get("display"),
        "rating": rating,
        "reviewCount": product.get("ratingsTotal"),
        "image": product.get("mainImageUrl"),
        "amazonUrl": f"https://www.amazon.com/dp/{asin}",

        "overallScore": overall_score,

        "reviewIntegrity": {
            "score": integrity_score,
            "label": review_integrity.get("integrity_label"),
            "verifiedPurchaseRatio": review_integrity.get("verified_purchase_ratio"),
            "sentimentConsistencyRatio": review_integrity.get("sentiment_consistency_ratio"),
            "flags": review_integrity.get("flags", {}),
            "commonKeywords": review_integrity.get("commonKeywords", []),
        },

        "brandReputation": {
            "score": reputation_score,
            "label": brand_reputation.get("overall_label"),
            "insights": brand_reputation.get("insights", []),
            "reviewsAnalyzed": brand_reputation.get("reviews_analyzed", 0),
            "commonKeywords": brand_reputation.get("commonKeywords", []),
            "source": brand_reputation.get("source"),
        },

        "aiAnalysis": {
            "pros": ai_analysis.get("pros", []),
            "cons": ai_analysis.get("cons", []),
            "verdict": ai_analysis.get("verdict", ""),
            "recommendation": ai_analysis.get("recommendation", "COMPARE"),
        },

        "similarProducts": [
            {
                "title": item.get("title"),
                "asin": item.get("asin"),
                "brand": item.get("brand"),
                "rating": item.get("rating"),
                "reviewCount": item.get("ratingsTotal"),
                "price": (item.get("price") or {}).get("display"),
                "isPrime": item.get("isPrime"),
                "image": item.get("mainImageUrl"),
                "amazonUrl": f"https://www.amazon.com/dp/{item.get('asin')}" if item.get("asin") else None,
            }
            for item in similar_products
            if isinstance(item, dict) and item.get("asin")
        ][:5],

        "raw": {
            "product": product,
            "reviews": reviews,
        },
    }