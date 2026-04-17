import re
from urllib.parse import unquote, urlparse

from .brand_reputation import get_brand_reputation
from .canopy_client import get_full_product_profile, search_similar_products
from .review_integrity import analyze_review_integrity

PRODUCT_KEYWORDS = [
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
    "charger",
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


def analyze_product_url(url: str) -> dict:
    asin = extract_asin(url)
    if not asin:
        raise ValueError("Could not find an Amazon ASIN in the provided URL.")

    product_keyword = extract_product_keyword(url)
    profile = get_full_product_profile(asin)

    product = profile.get("product", {})
    brand = profile.get("brand", "") or product.get("brand", "")

    review_integrity = analyze_review_integrity(profile.get("reviews", []))
    brand_reputation = get_brand_reputation(brand) if brand else {
        "brand": "",
        "reputation_score_pct": None,
        "overall_label": "Brand not found.",
        "insights": [],
        "reviews_analyzed": 0,
    }

    similar_products = []

    title = (product.get("title") or "").strip()
    brand_name = (brand or "").strip()

    # Use the real product info first, not the generic URL keyword
    search_term = " ".join(part for part in [brand_name, title] if part).strip()

    # Fallbacks if title/brand are missing
    if not search_term:
        search_term = product_keyword if product_keyword != "unknown" else ""

    if search_term:
        similar_products = search_similar_products(search_term)

    # If the first search is too specific or returns nothing, try a broader fallback
    if not similar_products and product_keyword != "unknown":
        similar_products = search_similar_products(product_keyword)

    rating = product.get("rating")
    integrity_score = review_integrity.get("integrity_score_pct", 50)
    reputation_score = brand_reputation.get("reputation_score_pct") or 50

    overall_score = build_overall_score(rating, integrity_score, reputation_score)

    return {
        "asin": asin,
        "productKeyword": product_keyword,
        "title": product.get("title"),
        "brand": brand,
        "price": (product.get("price") or {}).get("display"),
        "rating": rating,
        "reviewCount": product.get("ratingsTotal"),
        "image": product.get("mainImageUrl"), ## image available for Scanned product
        "amazonUrl": f"https://www.amazon.com/dp/{asin}", ## link available for Scanned product 

        "overallScore": overall_score,

        "reviewIntegrity": {
            "score": integrity_score,
            "label": review_integrity.get("integrity_label"),
            "verifiedPurchaseRatio": review_integrity.get("verified_purchase_ratio"),
            "sentimentConsistencyRatio": review_integrity.get("sentiment_consistency_ratio"),
            "flags": review_integrity.get("flags", {}),
        },

        "brandReputation": {
            "score": reputation_score,
            "label": brand_reputation.get("overall_label"),
            "insights": brand_reputation.get("insights", []),
            "reviewsAnalyzed": brand_reputation.get("reviews_analyzed", 0),
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
            if item.get("asin")
        ][:5],

        "raw": {
            "product": product,
            "reviews": profile.get("reviews", []),
        },
    }