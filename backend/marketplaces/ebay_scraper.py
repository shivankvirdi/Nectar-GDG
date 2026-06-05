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

# Same conservative timeouts as the Canopy adapter
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
                    raw = resp.json()

                    if isinstance(raw, list):
                        if not raw:
                            print(f"[eBay/ScraperAPI] Empty list response for {listing_id}")
                            return self._empty_profile(listing_id)
                        raw = raw[0]

                    if not isinstance(raw, dict):
                        print(
                            f"[eBay/ScraperAPI] Unexpected response type "
                            f"{type(raw).__name__} for {listing_id}"
                        )
                        return self._empty_profile(listing_id)

                    if not raw:
                        print(f"[eBay/ScraperAPI] Empty response for {listing_id}")
                        return self._empty_profile(listing_id)

                    product = self._normalize_product(raw)
                    reviews = self._normalize_reviews(raw)
                    seller = raw.get("seller") or {}

                    return {
                        "asin": listing_id,
                        "brand": seller.get("name", ""),
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

        results = resp.json().get("results", [])
        return [self._normalize_search_result(r) for r in results if isinstance(r, dict)]

    # ── Normalisation helpers ──────────────────────────────────────────────

    def _normalize_product(self, raw: dict) -> dict:
        """
        Map ScraperAPI eBay product fields → the same shape that Canopy
        produces, so the rest of the pipeline needs no changes.
        """
        price_val = None
        price_raw = raw.get("price") or {}
        if isinstance(price_raw, dict):
            v = price_raw.get("value")
            c = price_raw.get("currency", "USD")
            if v is not None:
                price_val = {"display": f"{c} {v}", "value": float(v)}
        elif isinstance(price_raw, (int, float)):
            price_val = {"display": f"${price_raw}", "value": float(price_raw)}

        return {
            "title":        raw.get("title"),
            "mainImageUrl": (raw.get("images") or [None])[0],
            "rating":       raw.get("rating"),
            "ratingsTotal": raw.get("review_count"),
            "brand":        raw.get("brand") or (raw.get("seller") or {}).get("name"),
            "price":        price_val,
            "featureBullets": [
                f"{s['label']}: {s['value']}"
                for s in (raw.get("item_specifics") or [])
                if s.get("label") and s.get("value")
            ],
            # eBay-specific extras (consumed downstream)
            "condition":    raw.get("condition"),
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
        for r in (raw.get("reviews") or []):
            if not isinstance(r, dict):
                continue

            body = (r.get("content") or r.get("text") or "").strip()
            if not body:
                continue

            # Verified purchase is nested inside attrs list
            verified = False
            for attr in (r.get("attrs") or []):
                if (attr.get("label") or "").lower() == "verified purchase":
                    verified = (attr.get("value") or "").strip().lower() == "yes"
                    break

            reviews.append({
                "title":           (r.get("title") or "").strip(),
                "body":            body,
                "rating":          r.get("stars", 3),
                "verifiedPurchase": verified,
            })
        return reviews

    def _normalize_search_result(self, r: dict) -> dict:
        """
        Map a ScraperAPI eBay search result item to the shape that
        vision_model.clean_similar_products() and the frontend expect.
        """
        price_val = None
        price_raw = r.get("price") or {}
        if isinstance(price_raw, dict):
            v = price_raw.get("value")
            c = price_raw.get("currency", "USD")
            if v is not None:
                price_val = {"display": f"{c} {v}", "value": float(v)}

        # Extract item ID from the result URL if asin/item_id not provided
        asin = r.get("item_id") or r.get("asin")
        if not asin:
            url = r.get("url") or ""
            m = re.search(r"/itm/(?:[^/]+/)?(\d{10,13})", url)
            if m:
                asin = m.group(1)

        return {
            "title":       r.get("title"),
            "asin":        asin,
            "brand":       r.get("seller") or r.get("brand"),
            "rating":      r.get("rating"),
            "ratingsTotal": r.get("review_count"),
            "mainImageUrl": r.get("image_url") or r.get("image"),
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