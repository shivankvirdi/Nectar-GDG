import sys
import os
import asyncio
import re
import time

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .vision_model import ScanCancelled, analyze_product_url
from .ai_analysis import build_recommendation_query, explain_score_with_ai
from .marketplaces.registry import MARKETPLACE_ADAPTERS

NECTAR_SECRET = os.getenv("NECTAR_API_SECRET", "")
MAX_RECOMMENDATION_CANDIDATES = 24
MAX_RECOMMENDATION_CANDIDATES_PER_TERM = 6
RECOMMENDATION_SEARCH_TIMEOUT_SECONDS = 16.0
RECOMMENDATION_AMAZON_SEARCH_TIMEOUT_SECONDS = 10.0
RECOMMENDATION_REFINED_TERM_LIMIT = 2
MIN_HISTORY_RECOMMENDATION_SOURCE_TERMS = 3
KNOWN_PROMPT_BRANDS = {
    "apple", "sony", "bose", "jbl", "samsung", "anker", "soundcore", "beats",
    "skullcandy", "google", "microsoft", "logitech", "razer", "steelseries",
    "carhartt", "nike", "adidas", "levi", "levis", "stanley", "hydro flask",
    "anua", "owala", "reebok", "under armour", "new balance", "asics", "puma",
    "brooks", "saucony", "hoka", "topo", "aeropostale",
}
PROMPT_PRODUCT_TERMS = {
    "airpods", "earbuds", "headphones", "speaker", "laptop", "keyboard", "mouse",
    "monitor", "camera", "charger", "case", "watch", "phone", "tablet", "vacuum",
    "backpack", "bottle", "shirt", "t-shirt", "tee", "shoes", "shoe", "sneakers",
    "running shoes", "hoodie", "jacket", "jeans", "air fryer", "coffee maker",
    "espresso machine", "blender", "toaster", "microwave", "kettle", "projector",
    "printer", "scanner", "router", "power bank", "cable", "drone", "microphone",
    "soundbar", "controller", "chair", "toothbrush", "bowling ball",
}
RELEVANCE_PROFILES = {
    "headphones": {
        "triggers": (
            "headphone", "headphones", "headset", "headsets", "earbud", "earbuds",
            "earphone", "earphones", "airpods", "over-ear", "over ear", "noise cancellation",
            "noise cancelling",
        ),
        "required": (
            "headphone", "headset", "earbud", "ear buds", "earphone",
            "airpods", "buds", "noise cancelling", "noise cancellation",
        ),
        "blocked": (
            "slipper", "slippers", "plush", "costume", "cosplay", "beanie",
            "hat", "stand", "holder", "case", "cover", "earmuff", "earmuffs",
        ),
    },
    "shoes": {
        "triggers": ("shoe", "shoes", "sneaker", "sneakers", "running shoes", "trainers"),
        "required": ("shoe", "shoes", "sneaker", "sneakers", "trainer", "trainers"),
        "blocked": (
            "slipper", "slippers", "sandal", "sandals", "sock", "socks",
            "shirt", "t-shirt", "tee", "hoodie", "jacket", "shorts", "pants",
        ),
    },
    "shirt": {
        "triggers": ("shirt", "shirts", "t-shirt", "tee", "pocket shirt"),
        "required": ("shirt", "t-shirt", "tee", "polo", "henley"),
        "blocked": ("pants", "jeans", "shoes", "slippers", "hat"),
    },
    "bowling_ball": {
        "triggers": ("bowling ball", "bowling balls"),
        "required": ("bowling ball", "bowling balls"),
        "blocked": ("bag", "bags", "shoe", "shoes", "cleaner", "polish", "towel"),
    },
}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UrlPayload(BaseModel):
    url: str
    scanId: str | None = None

class CancelScanPayload(BaseModel):
    scanId: str

class ExplainScorePayload(BaseModel):
    metric: str
    analysis: dict[str, Any]

class RecommendationsPayload(BaseModel):
    history: list[dict[str, Any]] = Field(default_factory=list)
    filter: str = "overall"
    prompt: str = ""
    imageDataUrl: str = ""
    marketplace: str = "all"

active_scan_cancellations: dict[str, asyncio.Event] = {}

def _infer_brand_from_title(title: str) -> str | None:
    text = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    if not text:
        return None
    for brand in sorted(KNOWN_PROMPT_BRANDS, key=len, reverse=True):
        normalized_brand = re.sub(r"[^a-z0-9]+", " ", brand.lower()).strip()
        if re.search(rf"\b{re.escape(normalized_brand)}\b", text):
            return brand.title()
    return None

def _price_display(item: dict[str, Any]) -> str | None:
    price = (
        item.get("price")
        or item.get("current_price")
        or item.get("currentPrice")
        or item.get("sale_price")
        or item.get("salePrice")
        or item.get("item_price")
        or item.get("itemPrice")
        or item.get("priceText")
        or item.get("price_display")
    )
    if isinstance(price, dict):
        display = price.get("display") or price.get("text") or price.get("formatted") or price.get("raw")
        if display:
            return str(display)
        value = price.get("value") or price.get("amount") or price.get("extracted")
        return f"${float(value):.2f}" if isinstance(value, (int, float)) else (str(value) if value else None)
    if isinstance(price, (str, int, float)):
        return str(price)
    return None

def _image_display(item: Any) -> str | None:
    if not item:
        return None
    if isinstance(item, str):
        image = item.strip()
        if not image:
            return None
        if image.startswith("//"):
            return f"https:{image}"
        if image.startswith(("http://", "https://", "data:image/")):
            return image
        return None
    if isinstance(item, dict):
        for key in ("url", "src", "link", "display", "large", "medium", "thumbnail", "imageUrl", "image_url"):
            image = _image_display(item.get(key))
            if image:
                return image
    if isinstance(item, list):
        for candidate in item:
            image = _image_display(candidate)
            if image:
                return image
    return None

def _numeric_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        raw = value.get("value") or value.get("amount") or value.get("display")
        return _numeric_price(raw)
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = re.search(r"\d+(?:,\d{3})*(?:\.\d{1,2})?", str(value))
    if not match:
        return None
    try:
        parsed = float(match.group(0).replace(",", ""))
        return parsed if parsed > 0 else None
    except ValueError:
        return None

def _numeric_rating(value: Any) -> float:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0

def _numeric_count(value: Any) -> int:
    if isinstance(value, int):
        return value
    cleaned = re.sub(r"[^0-9]", "", str(value or ""))
    return int(cleaned) if cleaned else 0

def _availability_text(item: dict[str, Any]) -> str:
    fields = [
        item.get("availability"),
        item.get("availabilityStatus"),
        item.get("stock"),
        item.get("stockStatus"),
        item.get("condition"),
        item.get("title"),
    ]
    return " ".join(str(field or "") for field in fields).lower()

def _is_available_recommendation(item: dict[str, Any]) -> bool:
    explicit_false_keys = ("isAvailable", "available", "inStock")
    for key in explicit_false_keys:
        if item.get(key) is False:
            return False

    text = _availability_text(item)
    unavailable_signals = (
        "currently unavailable",
        "out of stock",
        "sold out",
        "unavailable",
        "no longer available",
        "ended",
    )
    return not any(signal in text for signal in unavailable_signals)

def _normalize_recommendation_product(item: dict[str, Any], adapter) -> dict[str, Any] | None:
    listing_id = (
        item.get("asin")
        or item.get("listingId")
        or item.get("item_id")
        or item.get("itemId")
        or item.get("id")
    )
    listing_url = (
        item.get("listingUrl")
        or item.get("productUrl")
        or item.get("url")
        or item.get("link")
        or item.get("item_url")
        or item.get("itemUrl")
        or item.get("product_url")
    )
    if not listing_id and listing_url and adapter.name == "ebay":
        match = re.search(r"/itm/(?:[^/]+/)?(\d{10,13})", str(listing_url))
        listing_id = match.group(1) if match else None
    title = (item.get("title") or item.get("name") or item.get("product_title") or "").strip()
    if not listing_id or not title:
        return None
    price_display = _price_display(item)
    price_value = _numeric_price(price_display)
    if price_value is None or not price_display or not _is_available_recommendation(item):
        return None

    listing_url = str(listing_url or adapter.product_url(str(listing_id)))
    image = _image_display(
        item.get("mainImageUrl")
        or item.get("image")
        or item.get("image_url")
        or item.get("imageUrl")
        or item.get("thumbnail")
        or item.get("thumbnail_url")
        or item.get("thumbnailUrl")
        or item.get("images")
        or item.get("media")
    )
    return {
        "title": title,
        "asin": item.get("asin") or str(listing_id),
        "listingId": str(listing_id),
        "marketplace": adapter.name,
        "brand": item.get("brand") or item.get("seller_name") or item.get("store_name") or _infer_brand_from_title(title),
        "rating": item.get("rating"),
        "reviewCount": item.get("ratingsTotal") or item.get("reviewCount"),
        "price": price_display,
        "priceValue": price_value,
        "isPrime": item.get("isPrime"),
        "image": image,
        "listingUrl": listing_url,
        "productUrl": listing_url,
        "amazonUrl": listing_url if adapter.name == "amazon" else None,
    }

def _recommendation_rank(product: dict[str, Any], filter_mode: str) -> float:
    title = str(product.get("title") or "").lower()
    brand = str(product.get("brand") or "").lower()
    price = _numeric_price(product.get("priceValue") or product.get("price")) or 999999.0
    rating = _numeric_rating(product.get("rating"))
    reviews = _numeric_count(product.get("reviewCount"))
    review_score = min(reviews, 5000) / 5000
    prime_bonus = 0.08 if product.get("isPrime") else 0.0

    durable_terms = (
        "durable", "sturdy", "rugged", "reinforced", "waterproof", "water resistant",
        "metal", "aluminum", "steel", "long battery", "protective", "heavy duty",
        "military", "lifetime", "reliable",
    )
    quality_terms = (
        "premium", "pro", "professional", "high quality", "flagship", "top rated",
        "noise cancelling", "hi-res", "certified", "oled", "4k", "trusted",
    )

    durable_score = sum(1 for term in durable_terms if term in title or term in brand)
    quality_score = sum(1 for term in quality_terms if term in title or term in brand)

    if filter_mode == "price":
        return -price + (rating * 1.5) + (review_score * 4)
    if filter_mode == "durability":
        return (durable_score * 8) + (rating * 8) + (review_score * 10) + prime_bonus - (price / 1000)
    if filter_mode == "quality":
        return (quality_score * 8) + (rating * 10) + (review_score * 8) + prime_bonus
    return (rating * 8) + (review_score * 8) + prime_bonus - (price / 500)

def _source_term_bonus(product: dict[str, Any]) -> float:
    index = product.get("_sourceTermIndex")
    if not isinstance(index, int):
        return 0.0
    return max(0.0, 4.0 - index) * 4.0

def _sort_recommendations(products: list[dict[str, Any]], filter_mode: str) -> list[dict[str, Any]]:
    if filter_mode == "price":
        return sorted(
            products,
            key=lambda product: (
                product.get("_sourceTermIndex", 99),
                _numeric_price(product.get("priceValue") or product.get("price")) or 999999.0,
                -_numeric_rating(product.get("rating")),
                -_numeric_count(product.get("reviewCount")),
            ),
        )
    return sorted(
        products,
        key=lambda product: _recommendation_rank(product, filter_mode) + _source_term_bonus(product),
        reverse=True,
    )

def _history_default_query(history: list[dict[str, Any]]) -> str:
    for item in history[:8]:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue
        keyword = str(analysis.get("productKeyword") or "").strip()
        if keyword and keyword != "unknown":
            return keyword
        title = str(analysis.get("title") or "").strip()
        brand = str(analysis.get("brand") or "").strip()
        title_terms = _simple_title_terms(title, brand, keyword, include_brand=False)
        if title_terms:
            return title_terms[0]
    return "best value products"

def _clean_recommendation_query_text(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"\b(?:please|for me)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:at|with)\s+a\s+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:on|at|via|through)\s+(?:amazon(?:\.com)?|ebay(?:\.com)?)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:amazon(?:\.com)?|ebay(?:\.com)?)\b", " ", cleaned, flags=re.IGNORECASE)

    matched_brand = ""
    for brand in sorted(KNOWN_PROMPT_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", cleaned, flags=re.IGNORECASE):
            matched_brand = brand
            cleaned = re.sub(
                rf"\b(?:from|by|made\s+by)\s+{re.escape(brand)}\b",
                " ",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(rf"\b{re.escape(brand)}\b", " ", cleaned, flags=re.IGNORECASE)
            break

    cleaned = re.sub(r"\b(?:from|by|made\s+by)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if matched_brand:
        cleaned = f"{matched_brand} {cleaned}".strip()

    return cleaned

def _text_prompt_query(prompt: str, filter_mode: str) -> str:
    query = str(prompt or "").strip()
    query = re.sub(
        r"^\s*(show|find|get|search|recommend|give)\s+(me\s+)?",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\b(products?|items?|options?|suggestions?)\b", " ", query, flags=re.IGNORECASE)
    query = _clean_recommendation_query_text(query)

    suffix_by_filter = {
        "overall": "",
        "durability": "durable reliable",
        "price": "deals discounts best value",
        "quality": "top rated premium",
    }
    suffix = suffix_by_filter.get(filter_mode, "")
    if suffix and not re.search(r"\b(deal|deals|discount|discounts|discounted|sale|budget|cheap|premium|durable|reliable|top rated)\b", query, re.IGNORECASE):
        query = f"{query} {suffix}".strip()

    return query[:120] or "best value products"

def _prompt_has_product_target(prompt: str) -> bool:
    text = str(prompt or "").lower()
    if any(re.search(rf"\b{re.escape(brand)}\b", text) for brand in KNOWN_PROMPT_BRANDS):
        return True
    if any(re.search(rf"\b{re.escape(term)}\b", text) for term in PROMPT_PRODUCT_TERMS):
        return True
    return False

def _target_relevance_profile(query: str, prompt: str) -> dict[str, tuple[str, ...]] | None:
    text = f"{query} {prompt}".lower()
    for profile in RELEVANCE_PROFILES.values():
        if any(trigger in text for trigger in profile["triggers"]):
            return profile
    return None

def _product_matches_relevance(
    product: dict[str, Any],
    *,
    query: str,
    prompt: str,
    has_image_refinement: bool,
) -> bool:
    profile = _target_relevance_profile(query, prompt)
    if not profile:
        return True

    title = str(product.get("title") or "").lower()
    brand = str(product.get("brand") or "").lower()
    product_text = f"{title} {brand}"
    request_text = f"{query} {prompt}".lower()

    for blocked in profile["blocked"]:
        if blocked in product_text and blocked not in request_text:
            return False

    if any(required in product_text for required in profile["required"]):
        return True

    # Image searches should be strict because bad visual fallbacks look especially jarring.
    return not has_image_refinement

def _requested_marketplace_names(prompt: str) -> set[str]:
    text = str(prompt or "").lower()
    requested: set[str] = set()
    if re.search(r"\bamazon\b", text):
        requested.add("amazon")
    if re.search(r"\bebay\b", text):
        requested.add("ebay")
    return requested

def _prompt_requires_marketplace_lock(prompt: str) -> bool:
    text = str(prompt or "").lower()
    return bool(
        re.search(r"\b(?:only|just|exclusively)\s+(?:on|from|at|via)?\s*(?:amazon|ebay)\b", text)
        or re.search(r"\b(?:amazon|ebay)\s+only\b", text)
    )

def _ordered_recommendation_adapters(prompt: str, preferred_marketplace: str):
    requested = _requested_marketplace_names(prompt)
    adapters = list(MARKETPLACE_ADAPTERS)
    if requested and _prompt_requires_marketplace_lock(prompt):
        adapters = [adapter for adapter in adapters if adapter.name in requested]
    if not requested:
        return sorted(
            adapters,
            key=lambda adapter: (
                0 if adapter.name == "amazon" else 1,
                0 if adapter.name == preferred_marketplace else 1,
            ),
        )
    return sorted(
        adapters,
        key=lambda adapter: (
            0 if adapter.name == preferred_marketplace else 1,
            0 if adapter.name in requested else 1,
        ),
    )

def _filter_recommendation_adapters(adapters, marketplace: str):
    if marketplace in {"amazon", "ebay"}:
        return [adapter for adapter in adapters if adapter.name == marketplace]
    return adapters

def _recommendation_adapter_timeout(adapter) -> float:
    if adapter.name == "amazon":
        return RECOMMENDATION_AMAZON_SEARCH_TIMEOUT_SECONDS
    return RECOMMENDATION_SEARCH_TIMEOUT_SECONDS

async def _search_adapter_for_recommendations(adapter, term: str) -> list:
    started = time.perf_counter()
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(adapter.search_similar_products, term),
            timeout=_recommendation_adapter_timeout(adapter),
        )
        elapsed = time.perf_counter() - started
        print(f"[Recommendations] {adapter.name} search '{term}' returned {len(results or [])} items in {elapsed:.1f}s")
        return results if isinstance(results, list) else []
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - started
        print(f"[Recommendations] {adapter.name} search '{term}' timed out after {elapsed:.1f}s")
        return []
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(f"[Recommendations] {adapter.name} search '{term}' failed after {elapsed:.1f}s: {exc}")
        return []

async def _recommendation_search_job(term_index: int, term: str, adapter):
    results = await _search_adapter_for_recommendations(adapter, term)
    return term_index, term, adapter, results

def _brand_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

def _prompt_requests_brand_lock(prompt: str, history: list[dict[str, Any]]) -> bool:
    text = str(prompt or "").lower()
    if not text.strip():
        return False

    explicit_brand_terms = (
        "same brand",
        "this brand",
        "that brand",
        "specific brand",
        "only brand",
        "only from",
        "just from",
    )
    if any(term in text for term in explicit_brand_terms):
        return True

    if any(re.search(rf"\b{re.escape(brand)}\b", text) for brand in KNOWN_PROMPT_BRANDS):
        return True

    for item in history[:8]:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue
        brand = str(analysis.get("brand") or "").strip()
        if brand and re.search(rf"\b{re.escape(brand.lower())}\b", text):
            return True

    return False

def _prompt_requests_history_brand_lock(prompt: str, history: list[dict[str, Any]]) -> bool:
    text = str(prompt or "").lower()
    if not text.strip():
        return False

    if any(term in text for term in ("same brand", "this brand", "that brand")):
        return True

    for item in history[:8]:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue
        brand = str(analysis.get("brand") or "").strip()
        if brand and re.search(rf"\b{re.escape(brand.lower())}\b", text):
            return True

    return False

def _strip_history_brands(text: str, history: list[dict[str, Any]]) -> str:
    cleaned = str(text or "")

    for item in history[:8]:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue
        brand = str(analysis.get("brand") or "").strip()
        if brand:
            cleaned = re.sub(rf"\b{re.escape(brand)}\b", " ", cleaned, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", cleaned).strip()

def _diversify_recommendations(
    ranked_products: list[dict[str, Any]],
    *,
    limit: int = 5,
    max_per_brand: int = 2,
    max_per_source_term: int | None = None,
    max_per_marketplace: int | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    brand_counts: dict[str, int] = {}
    source_counts: dict[int, int] = {}
    marketplace_counts: dict[str, int] = {}

    for product in ranked_products:
        brand = _brand_key(product.get("brand"))
        marketplace = str(product.get("marketplace") or "")
        source_index = product.get("_sourceTermIndex")
        source_limited = (
            max_per_source_term is not None
            and isinstance(source_index, int)
            and source_counts.get(source_index, 0) >= max_per_source_term
        )
        marketplace_limited = (
            max_per_marketplace is not None
            and marketplace
            and marketplace_counts.get(marketplace, 0) >= max_per_marketplace
        )
        brand_limited = bool(brand and brand_counts.get(brand, 0) >= max_per_brand)
        if not source_limited and not marketplace_limited and not brand_limited:
            selected.append(product)
            if brand:
                brand_counts[brand] = brand_counts.get(brand, 0) + 1
            if isinstance(source_index, int):
                source_counts[source_index] = source_counts.get(source_index, 0) + 1
            if marketplace:
                marketplace_counts[marketplace] = marketplace_counts.get(marketplace, 0) + 1
        else:
            deferred.append(product)

        if len(selected) >= limit:
            break

    if len(selected) < limit and max_per_marketplace is not None:
        remaining_deferred: list[dict[str, Any]] = []
        for product in deferred:
            if len(selected) >= limit:
                remaining_deferred.append(product)
                continue
            marketplace = str(product.get("marketplace") or "")
            if marketplace and marketplace_counts.get(marketplace, 0) >= max_per_marketplace:
                remaining_deferred.append(product)
                continue
            selected.append(product)
            if marketplace:
                marketplace_counts[marketplace] = marketplace_counts.get(marketplace, 0) + 1
        deferred = remaining_deferred

    if len(selected) < limit:
        for product in deferred:
            selected.append(product)
            if len(selected) >= limit:
                break

    return selected[:limit]

def _has_enough_diverse_candidates(products: list[dict[str, Any]], filter_mode: str) -> bool:
    if len(products) < 8:
        return False
    ranked = _sort_recommendations(products, filter_mode)
    diversified = _diversify_recommendations(ranked, limit=5)
    brands = {_brand_key(product.get("brand")) for product in diversified if _brand_key(product.get("brand"))}
    return len(diversified) >= 5 and len(brands) >= 3

def _source_term_coverage(products: list[dict[str, Any]]) -> int:
    return len({
        product.get("_sourceTermIndex")
        for product in products
        if isinstance(product.get("_sourceTermIndex"), int)
    })

def _public_recommendation_product(product: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in product.items() if not str(key).startswith("_")}

def _recommendation_search_terms(
    query: str,
    prompt: str,
    history: list[dict[str, Any]],
    has_image_refinement: bool = False,
    include_history_terms: bool = True,
) -> list[str]:
    terms: list[str] = []
    history_terms: list[str] = []
    allow_brand_terms = _prompt_requests_history_brand_lock(prompt, history)
    query = query if allow_brand_terms else _strip_history_brands(query, history)

    def add_to(target: list[str], term: Any) -> None:
        text = str(term or "").strip()
        if text and text.lower() not in {t.lower() for t in target}:
            target.append(text)

    if include_history_terms:
        for item in history[:5]:
            analysis = item.get("analysis") if isinstance(item, dict) else {}
            if not isinstance(analysis, dict):
                continue

            title = analysis.get("title") or ""
            brand = analysis.get("brand") or ""
            keyword = analysis.get("productKeyword") or ""

            if keyword and keyword != "unknown":
                add_to(history_terms, keyword)
                if allow_brand_terms and brand:
                    add_to(history_terms, f"{brand} {keyword}")

            for term in _simple_title_terms(str(title), str(brand), str(keyword), include_brand=allow_brand_terms):
                add_to(history_terms, term)

    has_refinement = bool(str(prompt or "").strip()) or has_image_refinement

    if has_refinement:
        add_to(terms, query)
        for term in history_terms:
            add_to(terms, term)
    else:
        for term in history_terms:
            add_to(terms, term)
        add_to(terms, query)

    return terms[:8]

def _simple_title_terms(title: str, brand: str, keyword: str, *, include_brand: bool = False) -> list[str]:
    title = str(title or "").strip()
    brand = str(brand or "").strip()
    keyword = str(keyword or "").strip()
    terms: list[str] = []

    if keyword and keyword != "unknown":
        terms.append(keyword)
        if include_brand and brand:
            terms.append(f"{brand} {keyword}")

    if title:
        words = re.findall(r"[A-Za-z0-9]+", title)
        useful = [
            word for word in words
            if len(word) > 2 and word.lower() not in {
                "and", "with", "for", "the", "new", "from", "pack", "black",
                "white", "blue", "red", "green", "size",
            }
        ]
        if brand:
            useful = [word for word in useful if word.lower() != brand.lower()]
        if include_brand and brand and useful:
            terms.append(f"{brand} {' '.join(useful[:4])}")
        terms.append(" ".join(useful[:5]) or title)

    return terms

@app.middleware("http")
async def log_and_verify(request: Request, call_next):
    print(f"[REQUEST] {request.method} {request.url}")

    if request.url.path != "/health":
        token = request.headers.get("X-Nectar-Secret", "")
        if NECTAR_SECRET and token != NECTAR_SECRET:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    response = await call_next(request)
    print(f"[RESPONSE] Status: {response.status_code}")
    return response

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/current-url")
async def analyze_product(payload: UrlPayload):
    cancel_event: asyncio.Event | None = None

    if payload.scanId:
        cancel_event = asyncio.Event()
        active_scan_cancellations[payload.scanId] = cancel_event
    ...
    try:
        analysis = await analyze_product_url(
            payload.url,
            is_cancelled=cancel_event.is_set if cancel_event else None,
        )
        return {"ok": True, "analysis": analysis}

    except ScanCancelled:
        return {"ok": False, "cancelled": True}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception:
        import traceback

        print("\n" + "=" * 80)
        traceback.print_exc()
        print("=" * 80 + "\n")

        raise

@app.post("/cancel-scan")
async def cancel_scan(payload: CancelScanPayload):
    cancel_event = active_scan_cancellations.get(payload.scanId)
    if cancel_event:
        cancel_event.set()
    return {"ok": True, "cancelled": bool(cancel_event)}

@app.post("/explain-score")
async def explain_score(payload: ExplainScorePayload):
    try:
        answer = explain_score_with_ai(payload.metric, payload.analysis)
        return {"ok": True, **answer}
    except Exception as e:
        import traceback

        print("\n" + "=" * 80)
        traceback.print_exc()
        print("=" * 80 + "\n")

        raise

@app.post("/recommendations")
async def recommendations(payload: RecommendationsPayload):
    try:
        filter_mode = payload.filter if payload.filter in {"overall", "durability", "price", "quality"} else "overall"
        has_text_refinement = bool(payload.prompt.strip())
        has_image_refinement = bool(payload.imageDataUrl)
        has_refinement = has_text_refinement or has_image_refinement
        if has_image_refinement:
            query_result = await asyncio.to_thread(
                build_recommendation_query,
                payload.history,
                filter_mode,
                payload.prompt,
                payload.imageDataUrl,
            )
        elif has_text_refinement:
            query_result = {
                "query": _text_prompt_query(payload.prompt, filter_mode),
                "reason": "Using the product request directly.",
            }
        else:
            query_result = {
                "query": _history_default_query(payload.history),
                "reason": "Using recent scan history and the selected filter.",
            }
        query = query_result.get("query") or "best value products"
        brand_locked = _prompt_requests_brand_lock(payload.prompt, payload.history)
        history_brand_locked = _prompt_requests_history_brand_lock(payload.prompt, payload.history)
        raw_search_query = query if history_brand_locked else _strip_history_brands(query, payload.history)
        search_query = _clean_recommendation_query_text(raw_search_query) or "best value products"

        if query_result.get("rejected"):
            return {
                "ok": True,
                "rejected": True,
                "message": query_result.get("message") or "Sorry, I cannot help you with that",
                "query": "",
                "reason": query_result.get("reason"),
                "filter": filter_mode,
                "products": [],
            }

        marketplace_counts: dict[str, int] = {}
        for item in payload.history:
            analysis = item.get("analysis") if isinstance(item, dict) else {}
            if isinstance(analysis, dict):
                marketplace = analysis.get("marketplace")
                if marketplace:
                    marketplace_counts[marketplace] = marketplace_counts.get(marketplace, 0) + 1

        preferred_marketplace = max(marketplace_counts, key=marketplace_counts.get) if marketplace_counts else "amazon"
        requested_marketplaces = _requested_marketplace_names(payload.prompt)
        if requested_marketplaces:
            preferred_marketplace = next(iter(requested_marketplaces))
        elif has_text_refinement and _prompt_has_product_target(payload.prompt):
            preferred_marketplace = "amazon"
        marketplace_filter = payload.marketplace if payload.marketplace in {"all", "amazon", "ebay"} else "all"
        adapters = _filter_recommendation_adapters(
            _ordered_recommendation_adapters(payload.prompt, preferred_marketplace),
            marketplace_filter,
        )

        if not adapters:
            return {
                "ok": True,
                "query": search_query,
                "reason": "No supported marketplace matched that request.",
                "filter": filter_mode,
                "marketplace": marketplace_filter,
                "products": [],
            }

        include_history_terms = not (
            has_image_refinement
            or (has_text_refinement and _prompt_has_product_target(payload.prompt))
        )

        search_terms = _recommendation_search_terms(
            search_query,
            payload.prompt,
            payload.history,
            bool(payload.imageDataUrl),
            include_history_terms=include_history_terms,
        )
        if has_refinement:
            search_terms = search_terms[:RECOMMENDATION_REFINED_TERM_LIMIT]

        print(
            f"[Recommendations] query='{search_query}' filter='{filter_mode}' "
            f"marketplace='{marketplace_filter}' terms={search_terms} marketplaces={[adapter.name for adapter in adapters]}"
        )

        seen: set[str] = set()
        products: list[dict[str, Any]] = []
        raw_count = 0
        normalized_count = 0
        relevance_drop_count = 0
        duplicate_drop_count = 0
        term_counts: dict[tuple[int, str], int] = {}

        for term_index, term in enumerate(search_terms):
            for adapter in adapters:
                term_key = (term_index, adapter.name if marketplace_filter == "all" else "*")
                term_added = term_counts.get(term_key, 0)
                if (
                    term_added >= MAX_RECOMMENDATION_CANDIDATES_PER_TERM
                    or len(products) >= MAX_RECOMMENDATION_CANDIDATES
                ):
                    break

                results = await _search_adapter_for_recommendations(adapter, term)
                for raw in results:
                    raw_count += 1
                    if not isinstance(raw, dict):
                        continue
                    product = _normalize_recommendation_product(raw, adapter)
                    if not product:
                        continue
                    normalized_count += 1
                    if not _product_matches_relevance(
                        product,
                        query=search_query,
                        prompt=payload.prompt,
                        has_image_refinement=has_image_refinement,
                    ):
                        relevance_drop_count += 1
                        continue
                    key = product["listingId"]
                    if key in seen:
                        duplicate_drop_count += 1
                        continue
                    product["_sourceTerm"] = term
                    product["_sourceTermIndex"] = term_index
                    seen.add(key)
                    products.append(product)
                    term_added += 1
                    term_counts[term_key] = term_added
                    if (
                        term_added >= MAX_RECOMMENDATION_CANDIDATES_PER_TERM
                        or len(products) >= MAX_RECOMMENDATION_CANDIDATES
                    ):
                        break

            if len(products) >= MAX_RECOMMENDATION_CANDIDATES:
                break
            if has_refinement and term_index == 0 and len(products) >= 5:
                break
            if (
                not has_refinement
                and _source_term_coverage(products) >= min(MIN_HISTORY_RECOMMENDATION_SOURCE_TERMS, len(search_terms))
                and len(products) >= 5
            ):
                break
            if has_refinement and not brand_locked and _has_enough_diverse_candidates(products, filter_mode):
                break

        ranked_products = _sort_recommendations(products, filter_mode)
        available_marketplaces = {
            str(product.get("marketplace") or "")
            for product in ranked_products
            if product.get("marketplace")
        }
        final_products = (
            ranked_products[:5]
            if brand_locked
            else _diversify_recommendations(
                ranked_products,
                limit=5,
                max_per_source_term=None if has_refinement else 2,
                max_per_marketplace=3 if marketplace_filter == "all" and len(available_marketplaces) > 1 else None,
            )
        )
        print(
            "[Recommendations] pipeline "
            f"raw={raw_count} normalized={normalized_count} "
            f"relevance_dropped={relevance_drop_count} duplicates={duplicate_drop_count} "
            f"ranked={len(ranked_products)} final={len(final_products)}"
        )

        return {
            "ok": True,
            "query": search_query,
            "reason": query_result.get("reason"),
            "filter": filter_mode,
            "marketplace": marketplace_filter,
            "products": [_public_recommendation_product(product) for product in final_products],
        }
    except Exception:
        import traceback

        print("\n" + "=" * 80)
        traceback.print_exc()
        print("=" * 80 + "\n")

        raise
