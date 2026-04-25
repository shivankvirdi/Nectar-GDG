# vision_model.py
import re
from urllib.parse import unquote, urlparse
from .ai_analysis import get_ai_verdict

from .brand_reputation import get_brand_reputation
from .canopy_client import get_full_product_profile, search_similar_products
from .review_integrity import analyze_review_integrity

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

def normalize_url_text(url: str) -> str:
    parsed   = urlparse(url)
    raw_text = f"{parsed.netloc} {parsed.path} {parsed.query}"
    decoded  = unquote(raw_text).lower()
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
    return match.group(1).upper() if match else None


# ─── Score helpers ────────────────────────────────────────────────────────────

def build_overall_score(
    product_rating: float | int | None,
    integrity_score: int,
    reputation_score: int,
) -> int:
    rating_component = round((float(product_rating) / 5) * 100) if product_rating is not None else 0
    return round((rating_component * 0.4) + (integrity_score * 0.35) + (reputation_score * 0.25))


def detect_accessory_type(title: str, fallback_keyword: str) -> str:
    text = (title or "").lower()
    if "screen protector" in text or "tempered glass" in text: return "screen protector"
    if "phone case" in text or re.search(r"\bcase\b", text):   return "phone case"
    if "wireless charger" in text:                              return "wireless charger"
    if "charger" in text:                                       return "charger"
    if "cable" in text:                                         return "charging cable"
    if "power bank" in text:                                    return "power bank"
    return fallback_keyword if fallback_keyword != "unknown" else ""


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


def clean_similar_products(similar_products: list, original_asin: str) -> list:
    cleaned   = []
    seen_asins: set[str] = set()
    for item in similar_products:
        if not isinstance(item, dict):
            continue
        asin  = item.get("asin")
        title = (item.get("title") or "").strip()
        if not asin or asin == original_asin or asin in seen_asins or not title:
            continue
        seen_asins.add(asin)
        cleaned.append(item)
    return cleaned


def build_similar_search_terms(
    title: str, brand_name: str, product_keyword: str
) -> list[str]:
    title          = (title or "").strip()
    brand_name     = (brand_name or "").strip()
    accessory_type = detect_accessory_type(title, product_keyword)
    device_name    = extract_device_name(title)

    search_terms: list[str] = []
    if device_name and accessory_type:
        if accessory_type == "screen protector":
            search_terms.append(f"{device_name} tempered glass {accessory_type}")
        search_terms.append(f"{device_name} {accessory_type}")
    if brand_name and accessory_type:
        search_terms.append(f"{brand_name} {accessory_type}")
    if accessory_type:
        search_terms.append(accessory_type)
    if title:
        search_terms.append(title)

    seen:   set[str]  = set()
    deduped: list[str] = []
    for term in search_terms:
        k = term.lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(term)
    return deduped


# ─── Main analysis entry point ────────────────────────────────────────────────

async def analyze_product_url(url: str) -> dict:
    asin = extract_asin(url)
    if not asin:
        raise ValueError("Could not find an Amazon ASIN in the provided URL.")

    product_keyword = extract_product_keyword(url)
    profile         = get_full_product_profile(asin)

    product = profile.get("product", {})
    brand   = profile.get("brand", "") or product.get("brand", "")
    reviews = profile.get("reviews") or []

    review_integrity = analyze_review_integrity(reviews)

    brand_reputation = await get_brand_reputation(brand, reviews) if brand else {
        "brand":                "",
        "reputation_score_pct": None,
        "overall_label":        "Brand not found.",
        "insights":             [],
        "reviews_analyzed":     0,
        "commonKeywords":       [],
    }

    title      = (product.get("title") or "").strip()
    brand_name = (brand or "").strip()

    similar_products: list = []
    for term in build_similar_search_terms(title, brand_name, product_keyword):
        results = search_similar_products(term)
        if results:
            similar_products = results
            break
    similar_products = clean_similar_products(similar_products, asin)

    rating           = product.get("rating")
    integrity_score  = review_integrity.get("integrity_score_pct", 50)
    reputation_score = brand_reputation.get("reputation_score_pct") or 50
    overall_score    = build_overall_score(rating, integrity_score, reputation_score)

    ai_analysis = get_ai_verdict(
        title=title,
        reviews=reviews,
        overall_score=overall_score,
        integrity_score=integrity_score,
        reputation_score=reputation_score,
    )

    return {
        "asin":           asin,
        "productKeyword": product_keyword,
        "title":          product.get("title"),
        "brand":          brand,
        "price":          (product.get("price") or {}).get("display"),
        "rating":         rating,
        "reviewCount":    product.get("ratingsTotal"),
        "image":          product.get("mainImageUrl"),
        "amazonUrl":      f"https://www.amazon.com/dp/{asin}",

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
                "brand":       item.get("brand"),
                "rating":      item.get("rating"),
                "reviewCount": item.get("ratingsTotal"),
                "price":       (item.get("price") or {}).get("display"),
                "isPrime":     item.get("isPrime"),
                "image":       item.get("mainImageUrl"),
                "amazonUrl":   f"https://www.amazon.com/dp/{item.get('asin')}" if item.get("asin") else None,
            }
            for item in similar_products
            if isinstance(item, dict) and item.get("asin")
        ][:5],

        "raw": {
            "product": product,
            "reviews": reviews,
        },
    }