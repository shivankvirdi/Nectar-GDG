# backend/marketplaces/ebay_scraper.py
"""
eBay adapter powered by ScraperAPI's structured eBay endpoints.

Two endpoints are used:
  - /structured/ebay/product  → product detail, reviews, seller info
  - /structured/ebay/search   → similar product search results

Differences from the Amazon/Canopy adapter that callers must be aware of:
  - `brand` is set to the SELLER name, not a manufacturer brand, because
    eBay listings are seller-centric. The reputation pipeline therefore
    analyses *seller* reputation rather than brand reputation.
  - `reviews` are buyer reviews of the specific listing/product on eBay.
    They include verified-purchase flags and star ratings, so the existing
    review_integrity pipeline works without modification.
  - A `seller` key is added to the returned profile dict so that
    vision_model.py can build the seller-reputation block.
"""

import os
import re
import time
from urllib.parse import urlparse, parse_qs, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from .base import MarketplaceAdapter

load_dotenv()

SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")
PRODUCT_URL   = "https://api.scraperapi.com/structured/ebay/product"
SEARCH_URL    = "https://api.scraperapi.com/structured/ebay/search"


def _ensure_dict(value, fallback: dict | None = None) -> dict:
    """Safely coerce *value* to a dict.

    ScraperAPI frequently returns lists where a dict is expected.
    This helper normalises every possible shape so downstream code
    can safely call `.get()` without crashing.
    """
    if fallback is None:
        fallback = {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        # Walk into nested lists until we find a dict or run out
        for item in value:
            if isinstance(item, dict):
                return item
        return fallback
    return fallback


def _ensure_list(value) -> list:
    """Safely coerce *value* to a list."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _safe_str(value, default: str = "") -> str:
    """Return a plain string regardless of what ScraperAPI sends."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or value.get("text") or value.get("value") or default
    if isinstance(value, list):
        for item in value:
            s = _safe_str(item, "")
            if s:
                return s
        return default
    if value is not None:
        return str(value)
    return default

CONNECT_TIMEOUT = 10
READ_TIMEOUT    = 45
MAX_RETRIES     = 3
RETRY_BACKOFF   = 1.5


def _make_session() -> requests.Session:
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _parse_seller_positive_pct(review_str: str) -> float | None:
    """
    ScraperAPI returns seller_review as e.g. "99.4% positive".
    Parse that into a float (99.4) so we can use it as an aggregate score.
    Returns None if the string cannot be parsed.
    """
    if not review_str:
        return None
    match = re.search(r"([\d.]+)\s*%", review_str)
    return float(match.group(1)) if match else None


class EbayScraperAPIAdapter(MarketplaceAdapter):
    name = "ebay"

    # ── URL handling ───────────────────────────────────────────────────────

    def can_handle_url(self, url: str) -> bool:
        hostname = (urlparse(url or "").netloc or "").lower()
        return "ebay." in hostname

    def extract_listing_id(self, url: str) -> str | None:
        """
        Extract the 12-digit item ID from common eBay URL shapes:
          ebay.com/itm/123456789012
          ebay.com/itm/title-here/123456789012
          ebay.com/p/123456789012          (product page with EPID)
        Also handles query-string fallback (?item=123456789012).
        """
        decoded = unquote(url or "")

        # Path patterns — most specific first
        for pattern in (
            r"/itm/(?:[^/]+/)?(\d{10,13})(?:[/?]|$)",
            r"/p/(\d{10,13})(?:[/?]|$)",
            r"/i/(\d{10,13})(?:[/?]|$)",
        ):
            m = re.search(pattern, decoded)
            if m:
                return m.group(1)

        # Query-string fallback
        qs = parse_qs(urlparse(decoded).query)
        for key in ("item", "itemId", "ItemID"):
            for val in qs.get(key, []):
                if re.fullmatch(r"\d{10,13}", val):
                    return val

        return None

    def product_url(self, listing_id: str) -> str:
        return f"https://www.ebay.com/itm/{listing_id}"

    # ── Data fetching ──────────────────────────────────────────────────────

    def fetch_product_profile(self, listing_id: str) -> dict:
        print(f"[eBay/ScraperAPI] Fetching product for item ID: {listing_id}")

        if not SCRAPERAPI_KEY:
            raise RuntimeError("Missing SCRAPERAPI_KEY environment variable.")

        session = _make_session()
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 2):
            try:
                print(f"[eBay/ScraperAPI] Attempt {attempt} for {listing_id}")
                resp = session.get(
                    PRODUCT_URL,
                    params={"api_key": SCRAPERAPI_KEY, "product_id": listing_id},
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )

                if resp.status_code == 200:
                    try:
                        raw = resp.json()
                    except Exception as je:
                        print(f"[eBay/ScraperAPI] JSON decode failed: {je}")
                        return self._empty_profile(listing_id)

                    # Normalise top-level: could be a list, dict, or junk
                    raw = _ensure_dict(raw)
                    if not raw:
                        print(f"[eBay/ScraperAPI] Empty/unusable response for {listing_id}")
                        return self._empty_profile(listing_id)

                    print(f"[eBay/ScraperAPI] Raw response keys: {list(raw.keys())}")

                    product = self._normalize_product(raw)
                    reviews = self._normalize_reviews(raw)

                    # Seller — always ensure it's a dict
                    seller = _ensure_dict(raw.get("seller"))
                    seller_name = _safe_str(
                        seller.get("name") or seller.get("username"),
                        default="",
                    )

                    return {
                        "asin": listing_id,
                        "brand": seller_name,
                        "product": product,
                        "reviews": reviews,
                        "seller": seller,
                    }

                print(f"[eBay/ScraperAPI] HTTP {resp.status_code} on attempt {attempt}")

            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                print(f"[eBay/ScraperAPI] Attempt {attempt} error: {exc}")

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                print(f"[eBay/ScraperAPI] Non-retriable error: {exc}")
                break

            if attempt <= MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"[eBay/ScraperAPI] Waiting {wait:.1f}s before retry…")
                time.sleep(wait)

        if last_exc:
            print(f"[eBay/ScraperAPI] All attempts failed. Last: {last_exc}")

        session.close()
        return self._empty_profile(listing_id)

    def search_similar_products(self, search_term: str) -> list:
        if not SCRAPERAPI_KEY:
            return []

        session = _make_session()
        try:
            resp = session.get(
                SEARCH_URL,
                params={"api_key": SCRAPERAPI_KEY, "query": search_term},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.exceptions.RequestException as exc:
            print(f"[eBay/ScraperAPI] Search failed for '{search_term}': {exc}")
            return []
        finally:
            session.close()

        if resp.status_code != 200:
            print(f"[eBay/ScraperAPI] Search HTTP {resp.status_code}")
            return []

        raw = resp.json()
        if isinstance(raw, list):
            results = raw
        elif isinstance(raw, dict):
            results = raw.get("results") or raw.get("items") or []
        else:
            results = []
        return [self._normalize_search_result(r) for r in results if isinstance(r, dict)]

    # ── Normalisation helpers ──────────────────────────────────────────────

    def _normalize_product(self, raw: dict) -> dict:
        """
        Map ScraperAPI eBay product fields → the same shape that Canopy
        produces, so the rest of the pipeline needs no changes.
        """
        # ── Price ──────────────────────────────────────────────────────────
        price_val = None
        price_raw = _ensure_dict(raw.get("price"))
        if price_raw:
            v = price_raw.get("value")
            c = _safe_str(price_raw.get("currency"), "USD")
            if v is not None:
                try:
                    price_val = {"display": f"{c} {v}", "value": float(v)}
                except (TypeError, ValueError):
                    pass
        else:
            # Sometimes price is a bare number
            p = raw.get("price")
            if isinstance(p, (int, float)):
                price_val = {"display": f"${p}", "value": float(p)}
            elif isinstance(p, str):
                # "$29.99" or "29.99"
                cleaned = re.sub(r"[^\d.]", "", p)
                if cleaned:
                    try:
                        price_val = {"display": p, "value": float(cleaned)}
                    except ValueError:
                        pass

        # ── Images ─────────────────────────────────────────────────────────
        images = _ensure_list(raw.get("images"))
        main_image_url = None
        for img in images:
            if isinstance(img, str) and img:
                main_image_url = img
                break
            if isinstance(img, dict):
                main_image_url = img.get("url") or img.get("src") or img.get("link")
                if main_image_url:
                    break

        # ── Seller / brand names ───────────────────────────────────────────
        seller = _ensure_dict(raw.get("seller"))
        seller_name = _safe_str(seller.get("name") or seller.get("username"), "")

        brand_name = _safe_str(raw.get("brand"), "")

        # ── Feature bullets ────────────────────────────────────────────────
        feature_bullets = []
        for s in _ensure_list(raw.get("item_specifics")):
            if isinstance(s, dict):
                label = _safe_str(s.get("label"))
                value = _safe_str(s.get("value"))
                if label and value:
                    feature_bullets.append(f"{label}: {value}")
            elif isinstance(s, list) and len(s) >= 2:
                label = _safe_str(s[0])
                value = _safe_str(s[1])
                if label and value:
                    feature_bullets.append(f"{label}: {value}")
            elif isinstance(s, str) and s.strip():
                feature_bullets.append(s.strip())

        return {
            "title":        _safe_str(raw.get("title")),
            "mainImageUrl": main_image_url,
            "rating":       raw.get("rating"),
            "ratingsTotal": raw.get("review_count"),
            "brand":        brand_name or seller_name,
            "price":        price_val,
            "featureBullets": feature_bullets,
            # eBay-specific extras (consumed downstream)
            "condition":    _safe_str(raw.get("condition")),
            "soldItems":    raw.get("sold_items"),
            "watchers":     raw.get("watchers"),
            # Rating aspect scores (0-100 integers from ScraperAPI)
            "easyToUse":    raw.get("easy_to_use"),
            "wellDesigned": raw.get("well_designed"),
            "goodValue":    raw.get("good_value"),
            # Star-histogram breakdown
            "ratingHistogram": {
                "5": raw.get("rating_count_5stars", 0),
                "4": raw.get("rating_count_4stars", 0),
                "3": raw.get("rating_count_3stars", 0),
                "2": raw.get("rating_count_2stars", 0),
                "1": raw.get("rating_count_1star",  0),
            },
        }

    def _normalize_reviews(self, raw: dict) -> list[dict]:
        """
        Map ScraperAPI eBay review objects to the same shape that
        amazon_canopy._normalize_reviews() produces, so review_integrity.py
        and ai_analysis.py work without modification.
        """
        reviews = []
        raw_reviews = _ensure_list(raw.get("reviews"))

        for r in raw_reviews:
            r = _ensure_dict(r)
            if not r:
                continue

            body = _safe_str(r.get("content") or r.get("text") or r.get("body")).strip()
            if not body:
                continue

            # Verified purchase is nested inside attrs list
            verified = False
            attrs = _ensure_list(r.get("attrs"))
            for attr in attrs:
                if isinstance(attr, dict):
                    if _safe_str(attr.get("label")).lower() == "verified purchase":
                        verified = _safe_str(attr.get("value")).strip().lower() == "yes"
                        break
                elif isinstance(attr, list) and len(attr) >= 2:
                    if _safe_str(attr[0]).lower() == "verified purchase":
                        verified = _safe_str(attr[1]).strip().lower() == "yes"
                        break

            # Rating can come in various field names
            rating = r.get("stars") or r.get("rating") or 3
            try:
                rating = int(float(rating))
            except (TypeError, ValueError):
                rating = 3

            reviews.append({
                "title":           _safe_str(r.get("title")).strip(),
                "body":            body,
                "rating":          rating,
                "verifiedPurchase": verified,
            })
        return reviews

    def _normalize_search_result(self, r: dict) -> dict:
        """
        Map a ScraperAPI eBay search result item to the shape that
        vision_model.clean_similar_products() and the frontend expect.
        """
        # ── Price ──────────────────────────────────────────────────────────
        price_val = None
        price_raw = _ensure_dict(r.get("price"))
        if price_raw:
            v = price_raw.get("value")
            c = _safe_str(price_raw.get("currency"), "USD")
            if v is not None:
                try:
                    price_val = {"display": f"{c} {v}", "value": float(v)}
                except (TypeError, ValueError):
                    pass
        else:
            p = r.get("price")
            if isinstance(p, (int, float)):
                price_val = {"display": f"${p}", "value": float(p)}

        # ── Item ID ────────────────────────────────────────────────────────
        asin = _safe_str(r.get("item_id") or r.get("asin"), "")
        if not asin:
            url = _safe_str(r.get("url"), "")
            m = re.search(r"/itm/(?:[^/]+/)?(\d{10,13})", url)
            if m:
                asin = m.group(1)

        # ── Brand / seller name ────────────────────────────────────────────
        seller_d = _ensure_dict(r.get("seller"))
        brand_name = _safe_str(seller_d.get("name") or seller_d.get("username"), "")
        if not brand_name:
            brand_name = _safe_str(r.get("brand"), "")

        # ── Image ──────────────────────────────────────────────────────────
        image = _safe_str(r.get("image_url") or r.get("image") or r.get("thumbnail"), "")

        return {
            "title":       _safe_str(r.get("title")),
            "asin":        asin,
            "brand":       brand_name,
            "rating":      r.get("rating"),
            "ratingsTotal": r.get("review_count"),
            "mainImageUrl": image or None,
            "isPrime":     False,   # eBay doesn't have Prime
            "price":       price_val,
        }

    @staticmethod
    def _empty_profile(listing_id: str) -> dict:
        return {
            "asin":    listing_id,
            "brand":   "",
            "product": {},
            "reviews": [],
            "seller":  {},
            "error":   "Failed to fetch eBay product data from ScraperAPI",
        }