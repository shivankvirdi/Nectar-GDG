import sys
import os
import asyncio
import re

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

active_scan_cancellations: dict[str, asyncio.Event] = {}

def _price_display(item: dict[str, Any]) -> str | None:
    price = item.get("price")
    if isinstance(price, dict):
        return price.get("display")
    if isinstance(price, (str, int, float)):
        return str(price)
    return None

def _numeric_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        raw = value.get("value") or value.get("amount") or value.get("display")
        return _numeric_price(raw)
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    cleaned = re.sub(r"[^0-9.]", "", str(value))
    if not cleaned:
        return None
    try:
        parsed = float(cleaned)
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
    listing_id = item.get("asin") or item.get("listingId") or item.get("item_id")
    title = (item.get("title") or "").strip()
    if not listing_id or not title:
        return None
    price_display = _price_display(item)
    price_value = _numeric_price(item.get("price") if item.get("price") is not None else price_display)
    if price_value is None or not price_display or not _is_available_recommendation(item):
        return None

    listing_url = adapter.product_url(str(listing_id))
    return {
        "title": title,
        "asin": item.get("asin") or str(listing_id),
        "listingId": str(listing_id),
        "marketplace": adapter.name,
        "brand": item.get("brand"),
        "rating": item.get("rating"),
        "reviewCount": item.get("ratingsTotal") or item.get("reviewCount"),
        "price": price_display,
        "priceValue": price_value,
        "isPrime": item.get("isPrime"),
        "image": item.get("mainImageUrl") or item.get("image"),
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

def _sort_recommendations(products: list[dict[str, Any]], filter_mode: str) -> list[dict[str, Any]]:
    if filter_mode == "price":
        return sorted(
            products,
            key=lambda product: (
                _numeric_price(product.get("priceValue") or product.get("price")) or 999999.0,
                -_numeric_rating(product.get("rating")),
                -_numeric_count(product.get("reviewCount")),
            ),
        )
    return sorted(products, key=lambda product: _recommendation_rank(product, filter_mode), reverse=True)

def _recommendation_search_terms(
    query: str,
    prompt: str,
    history: list[dict[str, Any]],
    has_image_refinement: bool = False,
) -> list[str]:
    terms: list[str] = []
    history_terms: list[str] = []

    def add_to(target: list[str], term: Any) -> None:
        text = str(term or "").strip()
        if text and text.lower() not in {t.lower() for t in target}:
            target.append(text)

    for item in history[:5]:
        analysis = item.get("analysis") if isinstance(item, dict) else {}
        if not isinstance(analysis, dict):
            continue

        title = analysis.get("title") or ""
        brand = analysis.get("brand") or ""
        keyword = analysis.get("productKeyword") or ""

        if keyword and keyword != "unknown":
            add_to(history_terms, keyword)
            if brand:
                add_to(history_terms, f"{brand} {keyword}")

        for term in _simple_title_terms(str(title), str(brand), str(keyword)):
            add_to(history_terms, term)

    has_refinement = bool(str(prompt or "").strip()) or has_image_refinement

    if has_refinement:
        add_to(terms, query)
        add_to(terms, prompt)
        for term in history_terms:
            add_to(terms, term)
    else:
        for term in history_terms:
            add_to(terms, term)
        add_to(terms, query)

    return terms[:8]

def _simple_title_terms(title: str, brand: str, keyword: str) -> list[str]:
    title = str(title or "").strip()
    brand = str(brand or "").strip()
    keyword = str(keyword or "").strip()
    terms: list[str] = []

    if keyword and keyword != "unknown":
        terms.append(keyword)
        if brand:
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
        if brand and useful:
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
        query_result = await asyncio.to_thread(
            build_recommendation_query,
            payload.history,
            filter_mode,
            payload.prompt,
            payload.imageDataUrl,
        )
        query = query_result.get("query") or "best value products"

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
        adapters = sorted(
            MARKETPLACE_ADAPTERS,
            key=lambda adapter: 0 if adapter.name == preferred_marketplace else 1,
        )

        search_terms = _recommendation_search_terms(
            query,
            payload.prompt,
            payload.history,
            bool(payload.imageDataUrl),
        )
        seen: set[str] = set()
        products: list[dict[str, Any]] = []
        for term in search_terms:
            for adapter in adapters:
                results = await asyncio.to_thread(adapter.search_similar_products, term)
                for raw in results:
                    if not isinstance(raw, dict):
                        continue
                    product = _normalize_recommendation_product(raw, adapter)
                    if not product:
                        continue
                    key = product["listingId"]
                    if key in seen:
                        continue
                    seen.add(key)
                    products.append(product)
                    if len(products) >= 24:
                        break
                if len(products) >= 24:
                    break
            if len(products) >= 24:
                break

        ranked_products = _sort_recommendations(products, filter_mode)

        return {
            "ok": True,
            "query": query,
            "reason": query_result.get("reason"),
            "filter": filter_mode,
            "products": ranked_products[:5],
        }
    except Exception:
        import traceback

        print("\n" + "=" * 80)
        traceback.print_exc()
        print("=" * 80 + "\n")

        raise
