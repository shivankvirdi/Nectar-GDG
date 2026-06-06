# vision_model.py
import asyncio
import re
from typing import Callable
from urllib.parse import unquote, urlparse
from .ai_analysis import get_ai_verdict

from .brand_reputation import get_brand_reputation, build_reputation_insights
from .marketplaces import get_adapter_for_url
from .review_integrity import analyze_review_integrity


class ScanCancelled(Exception):
    pass


def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled and is_cancelled():
        raise ScanCancelled()


# ─── Product keyword list ────────────────────────────────────────────────────
PRODUCT_KEYWORDS = [
    "wireless earbuds", "wired earbuds", "noise cancelling headphones",
    "over ear headphones", "on ear headphones", "in ear monitors",
    "headphones", "earbuds", "soundbar", "subwoofer", "home theater",
    "bluetooth speaker", "smart speaker", "speaker", "microphone",
    "podcast microphone", "condenser microphone", "usb microphone",
    "record player", "turntable",
    "smart tv", "television", "4k monitor", "gaming monitor",
    "ultrawide monitor", "monitor", "projector", "portable projector",
    "gaming laptop", "laptop", "chromebook", "mechanical keyboard",
    "gaming keyboard", "keyboard", "gaming mouse", "wireless mouse",
    "computer mouse", "gaming mousepad", "mouse pad", "usb hub",
    "docking station", "laptop stand", "monitor arm", "monitor stand",
    "webcam", "ring light", "graphics card", "cpu cooler", "cpu", "ram",
    "ssd", "external hard drive", "hard drive", "flash drive", "sd card",
    "memory card", "router", "wifi extender", "mesh wifi", "printer",
    "3d printer", "scanner",
    "smartphone", "tablet", "ipad", "screen protector", "tempered glass",
    "phone case", "case",
    "wireless charger", "magsafe charger", "charging cable", "usb c cable",
    "lightning cable", "charger", "power bank", "solar charger", "cable",
    "mirrorless camera", "dslr camera", "action camera", "dash cam",
    "security camera", "doorbell camera", "trail camera", "camera lens",
    "camera", "drone", "gimbal", "tripod",
    "smart home hub", "smart bulb", "smart plug", "smart lock",
    "smart thermostat", "thermostat", "led strip", "led lights",
    "robot vacuum", "vacuum cleaner", "air purifier", "humidifier",
    "dehumidifier",
    "gaming console", "gaming headset", "gaming chair", "controller",
    "steering wheel",
    "smartwatch", "fitness tracker", "smart glasses", "vr headset", "watch",
    "air fryer", "instant pot", "pressure cooker", "slow cooker",
    "coffee maker", "espresso machine", "electric kettle", "blender",
    "food processor", "stand mixer", "toaster oven", "toaster",
    "rice cooker", "microwave",
    "electric toothbrush", "water flosser", "hair dryer",
    "hair straightener", "curling iron", "electric razor", "massage gun",
    "smart scale", "blood pressure monitor", "pulse oximeter",
    "backpack", "laptop bag", "laptop sleeve", "cable organizer",
    "desk organizer",
]


# ─── URL helpers ─────────────────────────────────────────────────────────────

def normalize_search_text(text: str) -> str:
    decoded = unquote(text or "").lower()
    return re.sub(r"[-_/+=%]+", " ", decoded)


def normalize_url_text(url: str) -> str:
    parsed   = urlparse(url)
    raw_text = f"{parsed.netloc} {parsed.path} {parsed.query}"
    return normalize_search_text(raw_text)


def extract_product_keyword_from_text(text: str) -> str:
    normalized = normalize_search_text(text)
    for keyword in sorted(PRODUCT_KEYWORDS, key=len, reverse=True):
        pattern = rf"\b{re.escape(keyword)}\b"
        if re.search(pattern, normalized):
            return keyword
    return "unknown"


def extract_product_keyword(url: str) -> str:
    return extract_product_keyword_from_text(normalize_url_text(url))


# ─── Score helpers ────────────────────────────────────────────────────────────

def build_overall_score(
    product_rating: float | int | None,
    integrity_score: int,
    reputation_score: int,
) -> int:
    """
    Standard score used for Amazon. Weights:
      40% product star rating, 35% review integrity, 25% brand reputation
    """
    rating_component = round((float(product_rating) / 5) * 100) if product_rating is not None else 0
    return round((rating_component * 0.4) + (integrity_score * 0.35) + (reputation_score * 0.25))


def build_ebay_overall_score(
    product_rating: float | int | None,
    integrity_score: int,
    seller_score: int,
    seller_positive_pct: float | None,
) -> int:
    """
    eBay-specific score. Seller reputation is weighted more heavily because
    eBay is seller-centric. Weights:
      30% product star rating, 25% review integrity, 45% seller reputation
    """
    rating_component = round((float(product_rating) / 5) * 100) if product_rating is not None else 0
    base = round((rating_component * 0.30) + (integrity_score * 0.25) + (seller_score * 0.45))

    if seller_positive_pct is not None:
        blended = round(base * 0.70 + seller_positive_pct * 0.30)
        return blended

    return base


# ─── eBay seller reputation ───────────────────────────────────────────────────

def _parse_seller_pct(review_str: str) -> float | None:
    """Parse '99.4% positive' → 99.4"""
    if not review_str:
        return None
    m = re.search(r"([\d.]+)\s*%", review_str)
    return float(m.group(1)) if m else None


async def get_seller_reputation(seller: dict, reviews: list, product: dict) -> dict:
    """
    Build a seller-reputation block for eBay listings.

    Uses the seller metadata (positive percentage, review count, top_rated flag)
    as the primary signal, and runs the product reviews through the existing
    NLP pipeline for keyword extraction and sentiment insights.
    """
    seller_name    = seller.get("name", "Unknown Seller")
    positive_pct   = _parse_seller_pct(seller.get("seller_review", ""))
    reviews_count  = seller.get("seller_reviews_count")
    top_rated      = seller.get("top_rated", False)

    normalised_reviews = [
        {
            "text":   r.get("body", ""),
            "title":  r.get("title", ""),
            "rating": r.get("rating", 3),
        }
        for r in reviews
        if r.get("body", "").strip()
    ]

    nlp_result = build_reputation_insights(
        normalised_reviews,
        brand_name=seller_name,
        source_name="ebay_product_reviews",
        aggregate_rating=(positive_pct / 20.0) if positive_pct is not None else None,
        aggregate_rating_count=reviews_count,
    )

    score = nlp_result.get("reputation_score_pct")

    if positive_pct is not None:
        if positive_pct >= 99.0:
            label = (
                f"Excellent seller — {positive_pct}% positive feedback across {reviews_count:,} ratings."
                if reviews_count
                else f"Excellent seller — {positive_pct}% positive feedback."
            )
        elif positive_pct >= 97.0:
            label = f"Good seller — {positive_pct}% positive feedback."
        elif positive_pct >= 90.0:
            label = f"Mixed seller reputation — only {positive_pct}% positive feedback."
        else:
            label = f"Low-trust seller — {positive_pct}% positive feedback. Consider alternatives."
    else:
        label = nlp_result.get("overall_label", "Seller reputation data unavailable.")

    insights = _build_seller_insights(
        seller,
        positive_pct,
        top_rated,
        normalised_reviews,
        product,
    )

    return {
        **nlp_result,
        "overall_label":     label,
        "insights":          insights,
        "source":            "ebay_seller_profile",
        "sellerName":        seller_name,
        "sellerPositivePct": positive_pct,
        "sellerReviewCount": reviews_count,
        "topRatedSeller":    top_rated,
    }


def _build_seller_insights(
    seller: dict,
    positive_pct: float | None,
    top_rated: bool,
    reviews: list,
    product: dict,
) -> list[dict]:
    """
    Build four seller-specific insight topics for eBay listings.
    All data is pulled from the normalized product dict which has
    estimatedDeliveryMin/Max, returnPolicy, condition at the top level.
    """
    from .nlp_utils import sia

    # ── Insight 1: Seller Trust ───────────────────────────────────────────
    if positive_pct is None:
        trust_status = "Unknown"
    elif positive_pct >= 99.0:
        trust_status = "Excellent"
    elif positive_pct >= 97.0:
        trust_status = "Good"
    elif positive_pct >= 90.0:
        trust_status = "Caution"
    else:
        trust_status = "Poor"

    if top_rated:
        trust_status = f"{trust_status} · Top Rated"

    # ── Insight 2: Shipping & Delivery ────────────────────────────────────
    delivery_min  = product.get("estimatedDeliveryMin")
    delivery_max  = product.get("estimatedDeliveryMax")
    shipping_cost = product.get("shippingCost")

    if delivery_min and delivery_max:
        shipping_status = f"{delivery_min} – {delivery_max}"
    elif delivery_min:
        shipping_status = f"Est. {delivery_min}"
    elif shipping_cost is not None:
        cost_str = str(shipping_cost).strip()
        shipping_status = "Free shipping" if cost_str in ("0", "0.0", "Free", "free") else f"Shipping: {cost_str}"
    else:
        shipping_status = "Estimate unavailable"

    # ── Insight 3: Item Condition ─────────────────────────────────────────
    condition = product.get("condition")

    accuracy_scores = []
    for r in reviews:
        text = (r.get("text") or "").lower()
        if any(kw in text for kw in [
            "described", "accurate", "exactly", "expected",
            "different", "mislead", "wrong", "not as",
        ]):
            accuracy_scores.append(sia.polarity_scores(r["text"])["compound"])

    if accuracy_scores:
        avg = sum(accuracy_scores) / len(accuracy_scores)
        if avg >= 0.05:
            accuracy_label = "Accurate"
        elif avg <= -0.05:
            accuracy_label = "Disputed"
        else:
            accuracy_label = "Mixed"
        quality_status = f"{condition} · {accuracy_label}" if condition else accuracy_label
    elif condition:
        quality_status = condition
    else:
        quality_status = "Not specified"

    # ── Insight 4: Returns & Support ─────────────────────────────────────
    return_policy = product.get("returnPolicy")
    if return_policy:
        return_text = str(return_policy).strip()
        if len(return_text) > 60:
            return_text = return_text[:57] + "…"
        return_status = return_text
    else:
        return_scores = []
        for r in reviews:
            text = (r.get("text") or "").lower()
            if any(kw in text for kw in ["return", "refund", "support", "seller", "response", "contact"]):
                return_scores.append(sia.polarity_scores(r["text"])["compound"])
        if return_scores:
            avg = sum(return_scores) / len(return_scores)
            return_status = "Positive" if avg >= 0.05 else "Caution" if avg <= -0.05 else "Neutral"
        else:
            return_status = "No return info"

    return [
        {"topic": "Seller Trust",        "status": trust_status},
        {"topic": "Shipping & Delivery", "status": shipping_status},
        {"topic": "Item Condition",      "status": quality_status},
        {"topic": "Returns & Support",   "status": return_status},
    ]


# ─── Accessory / keyword helpers ─────────────────────────────────────────────

def detect_accessory_type(title: str, fallback_keyword: str = "") -> str:
    text = (title or "").lower()
    if "screen protector" in text or "tempered glass" in text:
        return "screen protector"
    if re.search(
        r"\bphone case\b"
        r"|\bcase\b.{0,16}\b(?:iphone|samsung|galaxy|pixel|phone)\b"
        r"|\b(?:iphone|samsung|galaxy|pixel|phone)\b.{0,16}\bcase\b",
        text,
    ) and "charging case" not in text:
        return "phone case"
    if "wireless charger" in text or "magsafe" in text:
        return "wireless charger"
    if re.search(r"\bcharger\b", text):
        return "charger"
    if "power bank" in text:
        return "power bank"
    if "laptop sleeve" in text or "laptop bag" in text:
        return "laptop bag"
    if re.search(r"\bcable\b", text):
        return "charging cable"
    if "mouse pad" in text or "mousepad" in text:
        return "mouse pad"
    if "usb hub" in text:
        return "usb hub"
    if "docking station" in text:
        return "docking station"
    if fallback_keyword and fallback_keyword.lower() in _KNOWN_ACCESSORY_KEYWORDS:
        return fallback_keyword
    return ""


def extract_device_name(title: str) -> str:
    text     = (title or "").strip()
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


_TITLE_KEYWORD_PATTERNS: list[tuple[str, str]] = [
    (r"\biphone\b|\bgalaxy [sa]\d|\bpixel \d|\bandroid.{0,10}phone|5g.{0,6}phone", "smartphone"),
    (r"\bipad\b",                                                                    "tablet"),
    (r"\bairpods\b|\bgalaxy buds\b|\bbeats(?: fit pro| studio buds)?\b|\btws\b",    "wireless earbuds"),
    (r"\bmacbook\b",                                                                 "laptop"),
    (r"\bair fryer\b",                                                               "air fryer"),
    (r"\bespresso\b|\bcoffee maker\b",                                               "coffee maker"),
    (r"\binstant pot\b|\bpressure cooker\b",                                         "pressure cooker"),
    (r"\bhair dryer\b|\blow dryer\b",                                                "hair dryer"),
    (r"(?:smart|apple|galaxy|fitbit).{0,6}\bwatch\b|\bwearable\b",                  "smartwatch"),
    (r"\boled\b|\bqled\b|\b\d{2,3}[- ]inch.{0,10}tv\b|\btelevision\b",             "smart tv"),
]


def infer_keyword_from_title(title: str) -> str:
    direct_keyword = extract_product_keyword_from_text(title)
    if direct_keyword != "unknown":
        return direct_keyword
    text = (title or "").lower()
    for pattern, keyword in _TITLE_KEYWORD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return keyword
    return "unknown"


_ACCESSORY_TITLE_SIGNALS = (
    "screen protector", "tempered glass", "phone case", "charger",
    "charging cable", "power bank", "laptop sleeve", "laptop bag",
    "mouse pad", "mousepad", "usb hub", "docking station",
    " cable", "adapter", " skin", " pouch", " bumper", " mount",
    " holder", " stand", " dock", "case cover", "protective case",
    "replacement case", "silicone case", "ear tips", "earhooks",
)

_KNOWN_ACCESSORY_KEYWORDS = {
    "screen protector", "tempered glass", "phone case", "case",
    "wireless charger", "magsafe charger", "charging cable",
    "usb c cable", "lightning cable", "charger", "power bank",
    "solar charger", "cable", "laptop bag", "laptop sleeve",
    "cable organizer", "desk organizer", "mouse pad", "gaming mousepad",
    "laptop stand", "monitor arm", "monitor stand", "usb hub",
    "docking station",
}

_PRIMARY_FAMILY_PATTERNS: list[tuple[str, str]] = [
    (r"\bairpods\s+pro\b", "airpods pro"),
    (r"\bairpods\s+max\b", "airpods max"),
    (r"\bairpods\b", "airpods"),
    (r"\bgalaxy buds\b", "galaxy buds"),
    (r"\bbeats fit pro\b", "beats fit pro"),
    (r"\bbeats studio buds\b", "beats studio buds"),
]


def is_accessory_keyword(keyword: str) -> bool:
    return (keyword or "").lower() in _KNOWN_ACCESSORY_KEYWORDS


def resolve_effective_product_keyword(url_keyword: str, title: str) -> str:
    title_keyword       = infer_keyword_from_title(title)
    cleaned_url_keyword = (url_keyword or "").strip().lower()
    if title_keyword != "unknown":
        if cleaned_url_keyword in {"", "unknown"}:
            return title_keyword
        if is_accessory_keyword(cleaned_url_keyword) and not is_accessory_keyword(title_keyword):
            return title_keyword
    return cleaned_url_keyword or title_keyword or "unknown"


def extract_product_family(title: str) -> str:
    text = (title or "").lower()
    for pattern, family in _PRIMARY_FAMILY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return family
    return ""


def is_accessory_title(title: str) -> bool:
    text = (title or "").lower()
    if any(sig in text for sig in _ACCESSORY_TITLE_SIGNALS):
        return True
    return bool(re.search(
        r"\b(?:protective|silicone|replacement|shockproof|clear|magnetic)\b.{0,18}\bcase\b"
        r"|\bcase\b.{0,18}\b(?:cover|protector|shell|skin)\b"
        r"|\b(?:cover|protector|shell|skin)\b.{0,18}\bcase\b",
        text, re.IGNORECASE,
    ))


def clean_similar_products(
    similar_products: list,
    original_asin: str,
    original_title: str = "",
) -> list:
    cleaned:    list     = []
    seen_asins: set[str] = set()
    original_keyword = resolve_effective_product_keyword("unknown", original_title)
    filter_accessories = not bool(detect_accessory_type(original_title, original_keyword))

    for item in similar_products:
        if not isinstance(item, dict):
            continue
        asin  = item.get("asin")
        title = (item.get("title") or "").strip()
        if not asin or asin == original_asin or asin in seen_asins or not title:
            continue
        if filter_accessories and is_accessory_title(title):
            continue
        seen_asins.add(asin)
        cleaned.append(item)
    return cleaned


def build_similar_search_terms(
    title: str, brand_name: str, product_keyword: str
) -> list[str]:
    title      = (title or "").strip()
    brand_name = (brand_name or "").strip()
    effective_keyword = resolve_effective_product_keyword(product_keyword, title)
    accessory_type    = detect_accessory_type(title, effective_keyword)
    device_name       = extract_device_name(title)
    product_family    = extract_product_family(title)

    search_terms: list[str] = []

    if accessory_type:
        if device_name:
            if accessory_type == "screen protector":
                search_terms.append(f"{device_name} tempered glass screen protector")
            search_terms.append(f"{device_name} {accessory_type}")
        if brand_name:
            search_terms.append(f"{brand_name} {accessory_type}")
        search_terms.append(accessory_type)
        if title:
            search_terms.append(title)
    else:
        if product_family and effective_keyword and product_family not in effective_keyword:
            search_terms.append(f"{product_family} {effective_keyword}")
        if product_family:
            search_terms.append(product_family)
        if brand_name and effective_keyword and effective_keyword != "unknown":
            search_terms.append(f"{brand_name} {effective_keyword}")
        if effective_keyword and effective_keyword != "unknown":
            search_terms.append(effective_keyword)
        if not search_terms and title:
            search_terms.append(title)

    seen:    set[str]  = set()
    deduped: list[str] = []
    for term in search_terms:
        k = term.lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(term)
    return deduped


# ─── Main analysis entry point ────────────────────────────────────────────────

async def analyze_product_url(
    url: str,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict:
    _raise_if_cancelled(is_cancelled)

    marketplace    = get_adapter_for_url(url)
    listing_id     = marketplace.extract_listing_id(url)
    is_ebay        = marketplace.name == "ebay"

    if not listing_id:
        raise ValueError(
            f"Could not find a {marketplace.name} listing ID in the provided URL."
        )

    product_keyword = extract_product_keyword(url)
    profile         = await asyncio.to_thread(marketplace.fetch_product_profile, listing_id)
    _raise_if_cancelled(is_cancelled)

    product = profile.get("product", {})
    if not isinstance(product, dict):
        product = {}
    reviews = profile.get("reviews") or []
    if not isinstance(reviews, list):
        reviews = []

    # ── Review integrity ──────────────────────────────────────────────────
    review_integrity = analyze_review_integrity(reviews)
    _raise_if_cancelled(is_cancelled)

    # ── Reputation: brand (Amazon) vs seller (eBay) ───────────────────────
    if is_ebay:
        seller = profile.get("seller", {})
        if not isinstance(seller, dict):
            seller = {}
        reputation_result = await get_seller_reputation(seller, reviews, product)
        brand = (
            seller.get("name", "")
            if isinstance(seller.get("name"), str)
            else ""
        ) or str(profile.get("brand", "") or "")
    else:
        brand = profile.get("brand", "") or product.get("brand", "")
        if brand:
            reputation_result = await asyncio.to_thread(
                lambda: asyncio.run(get_brand_reputation(brand, reviews))
            )
        else:
            reputation_result = {
                "brand":                "",
                "reputation_score_pct": None,
                "overall_label":        "Brand not found.",
                "insights":             [],
                "reviews_analyzed":     0,
                "commonKeywords":       [],
            }

    _raise_if_cancelled(is_cancelled)

    title                    = (product.get("title") or "").strip()
    brand_name               = brand.strip()
    resolved_product_keyword = resolve_effective_product_keyword(product_keyword, title)

    # ── Similar products ──────────────────────────────────────────────────
    similar_products = []

    embedded_similars = (
        product.get("similarItems", [])
        or product.get("relatedItems", [])
    )

    if embedded_similars:
        similar_products = [
            marketplace._normalize_search_result(item)
            for item in embedded_similars
            if isinstance(item, dict)
        ]
    else:
        for term in build_similar_search_terms(
            title,
            brand_name,
            resolved_product_keyword,
        ):
            search_results = await asyncio.to_thread(
                marketplace.search_similar_products,
                term,
            )

            results = clean_similar_products(
                search_results,
                listing_id,
                title,
            )

            if results:
                similar_products = results
                break

    # ── Scores ────────────────────────────────────────────────────────────
    rating           = product.get("rating")
    integrity_score  = review_integrity.get("integrity_score_pct", 50)
    reputation_score = reputation_result.get("reputation_score_pct") or 50

    if is_ebay:
        seller_pct    = reputation_result.get("sellerPositivePct")
        overall_score = build_ebay_overall_score(
            rating, integrity_score, reputation_score, seller_pct
        )
    else:
        overall_score = build_overall_score(rating, integrity_score, reputation_score)

    # ── AI analysis ───────────────────────────────────────────────────────
    _raise_if_cancelled(is_cancelled)
    ai_analysis = await asyncio.to_thread(
        get_ai_verdict,
        title=title,
        reviews=reviews,
        overall_score=overall_score,
        integrity_score=integrity_score,
        reputation_score=reputation_score,
        marketplace=marketplace.name,
    )
    _raise_if_cancelled(is_cancelled)

    # ── Build output keys ─────────────────────────────────────────────────
    integrity_key  = "sellerReviewIntegrity" if is_ebay else "reviewIntegrity"
    reputation_key = "sellerReputation"      if is_ebay else "brandReputation"

    return {
        "asin":           listing_id,
        "marketplace":    marketplace.name,
        "listingId":      listing_id,
        "listingUrl":     marketplace.product_url(listing_id),
        "productKeyword": resolved_product_keyword,
        "title":          product.get("title"),
        "brand":          brand,
        "price":          (product.get("price") or {}).get("display"),
        "rating":         rating,
        "reviewCount":    product.get("ratingsTotal"),
        "image":          product.get("mainImageUrl"),
        "amazonUrl":      marketplace.product_url(listing_id),

        "overallScore": overall_score,

        integrity_key: {
            "score":                     integrity_score,
            "label":                     review_integrity.get("integrity_label"),
            "verifiedPurchaseRatio":     review_integrity.get("verified_purchase_ratio"),
            "sentimentConsistencyRatio": review_integrity.get("sentiment_consistency_ratio"),
            "flags":                     review_integrity.get("flags", {}),
            "commonKeywords":            review_integrity.get("commonKeywords", []),
        },

        reputation_key: {
            "score":           reputation_score,
            "label":           reputation_result.get("overall_label"),
            "insights":        reputation_result.get("insights", []),
            "reviewsAnalyzed": reputation_result.get("reviews_analyzed", 0),
            "commonKeywords":  reputation_result.get("commonKeywords", []),
            "source":          reputation_result.get("source"),
            # eBay-only extras (ignored by frontend for Amazon)
            "isSellerReputation": is_ebay,
            "sellerName":         reputation_result.get("sellerName"),
            "sellerPositivePct":  reputation_result.get("sellerPositivePct"),
            "sellerReviewCount":  reputation_result.get("sellerReviewCount"),
            "topRatedSeller":     reputation_result.get("topRatedSeller"),
        },

        "aiAnalysis": {
            "pros":           ai_analysis.get("pros", []),
            "cons":           ai_analysis.get("cons", []),
            "verdict":        ai_analysis.get("verdict", ""),
            "recommendation": ai_analysis.get("recommendation", "COMPARE"),
        },

        "similarProducts": [
            {
                "title":       item.get("title"),
                "asin":        item.get("asin"),
                "listingId":   item.get("asin"),
                "brand":       item.get("brand"),
                "rating":      item.get("rating"),
                "reviewCount": item.get("ratingsTotal"),
                "price":       (item.get("price") or {}).get("display"),
                "isPrime":     item.get("isPrime"),
                "image":       item.get("mainImageUrl"),
                "listingUrl":  marketplace.product_url(item.get("asin")) if item.get("asin") else None,
                "amazonUrl":   marketplace.product_url(item.get("asin")) if item.get("asin") else None,
            }
            for item in similar_products
            if isinstance(item, dict) and item.get("asin")
        ][:5],

        "raw": {
            "product": product,
            "reviews": reviews,
        },
    }