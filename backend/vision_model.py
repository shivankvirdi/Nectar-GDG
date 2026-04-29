# vision_model.py
import asyncio
import re
from typing import Callable
from urllib.parse import unquote, urlparse
from .ai_analysis import get_ai_verdict

from .brand_reputation import get_brand_reputation
from .marketplaces import get_adapter_for_url
from .review_integrity import analyze_review_integrity


class ScanCancelled(Exception):
    pass


def _raise_if_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled and is_cancelled():
        raise ScanCancelled()

# ─── Product keyword list ───────────────────────────────────────────
# Rules:
#  1. Longest / most specific phrases must come BEFORE shorter ones so the
#     regex finds "wireless earbuds" before "earbuds", "gaming console" before
#     "console", etc. The list is re-sorted by length at runtime so ordering
#     here doesn't matter — just be thorough.
#  2. Use the exact words a shopper or Amazon URL would contain.

PRODUCT_KEYWORDS = [
    # ── Audio ──────────────────────────────────────────────────────────────
    "wireless earbuds",
    "wired earbuds",
    "noise cancelling headphones",
    "over ear headphones",
    "on ear headphones",
    "in ear monitors",
    "headphones",
    "earbuds",
    "soundbar",
    "subwoofer",
    "home theater",
    "bluetooth speaker",
    "smart speaker",
    "speaker",
    "microphone",
    "podcast microphone",
    "condenser microphone",
    "usb microphone",
    "record player",
    "turntable",

    # ── Displays ───────────────────────────────────────────────────────────
    "smart tv",
    "television",
    "4k monitor",
    "gaming monitor",
    "ultrawide monitor",
    "monitor",
    "projector",
    "portable projector",

    # ── Computers & peripherals ────────────────────────────────────────────
    "gaming laptop",
    "laptop",
    "chromebook",
    "mechanical keyboard",
    "gaming keyboard",
    "keyboard",
    "gaming mouse",
    "wireless mouse",
    "computer mouse",
    "gaming mousepad",
    "mouse pad",
    "usb hub",
    "docking station",
    "laptop stand",
    "monitor arm",
    "monitor stand",
    "webcam",
    "ring light",
    "graphics card",
    "cpu cooler",
    "cpu",
    "ram",
    "ssd",
    "external hard drive",
    "hard drive",
    "flash drive",
    "sd card",
    "memory card",
    "router",
    "wifi extender",
    "mesh wifi",
    "printer",
    "3d printer",
    "scanner",

    # ── Mobile & tablets ──────────────────────────────────────────────────
    "smartphone",
    "tablet",
    "ipad",
    "screen protector",
    "tempered glass",
    "phone case",
    "case",

    # ── Charging & power ──────────────────────────────────────────────────
    "wireless charger",
    "magsafe charger",
    "charging cable",
    "usb c cable",
    "lightning cable",
    "charger",
    "power bank",
    "solar charger",
    "cable",

    # ── Cameras & imaging ─────────────────────────────────────────────────
    "mirrorless camera",
    "dslr camera",
    "action camera",
    "dash cam",
    "security camera",
    "doorbell camera",
    "trail camera",
    "camera lens",
    "camera",
    "drone",
    "gimbal",
    "tripod",

    # ── Smart home ────────────────────────────────────────────────────────
    "smart home hub",
    "smart bulb",
    "smart plug",
    "smart lock",
    "smart thermostat",
    "thermostat",
    "led strip",
    "led lights",
    "robot vacuum",
    "vacuum cleaner",
    "air purifier",
    "humidifier",
    "dehumidifier",

    # ── Gaming ────────────────────────────────────────────────────────────
    "gaming console",
    "gaming headset",
    "gaming chair",
    "controller",
    "steering wheel",

    # ── Wearables ─────────────────────────────────────────────────────────
    "smartwatch",
    "fitness tracker",
    "smart glasses",
    "vr headset",
    "watch",

    # ── Kitchen appliances ────────────────────────────────────────────────
    "air fryer",
    "instant pot",
    "pressure cooker",
    "slow cooker",
    "coffee maker",
    "espresso machine",
    "electric kettle",
    "blender",
    "food processor",
    "stand mixer",
    "toaster oven",
    "toaster",
    "rice cooker",
    "microwave",

    # ── Personal care & health ────────────────────────────────────────────
    "electric toothbrush",
    "water flosser",
    "hair dryer",
    "hair straightener",
    "curling iron",
    "electric razor",
    "massage gun",
    "smart scale",
    "blood pressure monitor",
    "pulse oximeter",

    # ── Bags & organisation ───────────────────────────────────────────────
    "backpack",
    "laptop bag",
    "laptop sleeve",
    "cable organizer",
    "desk organizer",
]


# ─── URL helpers ──────────────────────────────────────────────────────────────

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
    rating_component = round((float(product_rating) / 5) * 100) if product_rating is not None else 0
    return round((rating_component * 0.4) + (integrity_score * 0.35) + (reputation_score * 0.25))


def detect_accessory_type(title: str, fallback_keyword: str = "") -> str:
    """
    Return the accessory-type string when the product is a device accessory,
    or an empty string when it is a primary/standalone product.

    The fallback_keyword is only echoed back when it is a known accessory
    category — primary-product keywords like 'smartphone' are never returned.
    """
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

    # Only fall back to the caller's keyword when it is a genuine accessory term
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

# Title-based category inference

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
    """Infer product category from the product title when URL extraction fails."""
    direct_keyword = extract_product_keyword_from_text(title)
    if direct_keyword != "unknown":
        return direct_keyword

    text = (title or "").lower()
    for pattern, keyword in _TITLE_KEYWORD_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return keyword
    return "unknown"


# Accessory detection helpers

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
    """
    Prefer the title-inferred keyword when the URL only exposes an accessory
    token like "case" but the product title clearly describes a primary item.
    """
    title_keyword = infer_keyword_from_title(title)
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
    """Return True when a product title looks like a device accessory."""
    text = (title or "").lower()
    if any(sig in text for sig in _ACCESSORY_TITLE_SIGNALS):
        return True

    return bool(re.search(
        r"\b(?:protective|silicone|replacement|shockproof|clear|magnetic)\b.{0,18}\bcase\b"
        r"|\bcase\b.{0,18}\b(?:cover|protector|shell|skin)\b"
        r"|\b(?:cover|protector|shell|skin)\b.{0,18}\bcase\b",
        text,
        re.IGNORECASE,
    ))

def clean_similar_products(
    similar_products: list,
    original_asin: str,
    original_title: str = "",
) -> list:
    """
    Deduplicate results and, when the scanned product is a primary device,
    filter out obvious accessories (cases, chargers, cables…) that Canopy
    occasionally returns even for category searches.
    """
    cleaned:    list     = []
    seen_asins: set[str] = set()

    # Apply the accessory filter only when the scanned item is itself a
    # primary product; skip it for legitimate accessory-vs-accessory searches.
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

    # Resolve effective category keyword; fall back to title-based inference
    # when the URL didn't contain a recognisable product word (e.g. iphone URLs).
    effective_keyword = resolve_effective_product_keyword(product_keyword, title)

    # Detect genuine accessory type (returns "" for primary products)
    accessory_type = detect_accessory_type(title, effective_keyword)
    device_name    = extract_device_name(title)
    product_family = extract_product_family(title)

    search_terms: list[str] = []

    if accessory_type:
        # ── ACCESSORY ─────────────────────────────────────────────────────
        # Search for the same accessory type for the same device, so the
        # user sees competing cases/chargers rather than unrelated products.
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
        # ── PRIMARY PRODUCT ───────────────────────────────────────────────
        # Search by *category keyword only* — do NOT include the device name.
        # "iPhone 15 Pro smartphone" returns iPhone accessories; "smartphone"
        # returns competing phones from other brands.
        if product_family and effective_keyword and product_family not in effective_keyword:
            search_terms.append(f"{product_family} {effective_keyword}")
        if product_family:
            search_terms.append(product_family)
        if brand_name and effective_keyword and effective_keyword != "unknown":
            search_terms.append(f"{brand_name} {effective_keyword}")
        if effective_keyword and effective_keyword != "unknown":
            search_terms.append(effective_keyword)
        # Fall back to full title only when no category could be determined
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

    marketplace = get_adapter_for_url(url)
    listing_id = marketplace.extract_listing_id(url)
    if not listing_id:
        raise ValueError(f"Could not find a {marketplace.name} listing ID in the provided URL.")

    product_keyword = extract_product_keyword(url)
    profile         = await asyncio.to_thread(marketplace.fetch_product_profile, listing_id)
    _raise_if_cancelled(is_cancelled)

    product = profile.get("product", {})
    brand   = profile.get("brand", "") or product.get("brand", "")
    reviews = profile.get("reviews") or []

    review_integrity = analyze_review_integrity(reviews)
    _raise_if_cancelled(is_cancelled)

    brand_reputation = await asyncio.to_thread(
        lambda: asyncio.run(get_brand_reputation(brand, reviews))
    ) if brand else {
        "brand":                "",
        "reputation_score_pct": None,
        "overall_label":        "Brand not found.",
        "insights":             [],
        "reviews_analyzed":     0,
        "commonKeywords":       [],
    }
    _raise_if_cancelled(is_cancelled)

    title                    = (product.get("title") or "").strip()
    brand_name               = (brand or "").strip()
    resolved_product_keyword = resolve_effective_product_keyword(product_keyword, title)

    similar_products: list = []
    for term in build_similar_search_terms(title, brand_name, resolved_product_keyword):
        _raise_if_cancelled(is_cancelled)
        search_results = await asyncio.to_thread(marketplace.search_similar_products, term)
        _raise_if_cancelled(is_cancelled)
        results = clean_similar_products(search_results, listing_id, title)
        if results:
            similar_products = results
            break

    rating           = product.get("rating")
    integrity_score  = review_integrity.get("integrity_score_pct", 50)
    reputation_score = brand_reputation.get("reputation_score_pct") or 50
    overall_score    = build_overall_score(rating, integrity_score, reputation_score)

    _raise_if_cancelled(is_cancelled)
    ai_analysis = await asyncio.to_thread(
        get_ai_verdict,
        title=title,
        reviews=reviews,
        overall_score=overall_score,
        integrity_score=integrity_score,
        reputation_score=reputation_score,
    )
    _raise_if_cancelled(is_cancelled)

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

        "reviewIntegrity": {
            "score":                     integrity_score,
            "label":                     review_integrity.get("integrity_label"),
            "verifiedPurchaseRatio":     review_integrity.get("verified_purchase_ratio"),
            "sentimentConsistencyRatio": review_integrity.get("sentiment_consistency_ratio"),
            "flags":                     review_integrity.get("flags", {}),
            "commonKeywords":            review_integrity.get("commonKeywords", []),
        },

        "brandReputation": {
            "score":           reputation_score,
            "label":           brand_reputation.get("overall_label"),
            "insights":        brand_reputation.get("insights", []),
            "reviewsAnalyzed": brand_reputation.get("reviews_analyzed", 0),
            "commonKeywords":  brand_reputation.get("commonKeywords", []),
            "source":          brand_reputation.get("source"),
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
