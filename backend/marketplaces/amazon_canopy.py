import os
import re
import time
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from ..budget_config import BUDGET_MIN, BUDGET_MAX
from .base import MarketplaceAdapter

load_dotenv()

API_KEY = os.getenv("CANOPY_API_KEY")
CANOPY_URL = "https://graphql.canopyapi.co/"

if not API_KEY:
    raise RuntimeError("Missing CANOPY_API_KEY environment variable.")

HEADERS = {
    "Content-Type": "application/json",
    "API-KEY": API_KEY,
}

# Timeout config — connect fast, give the read plenty of room
CONNECT_TIMEOUT = 10   # seconds to establish TCP connection
READ_TIMEOUT    = 45   # seconds to wait for the server to send data
MAX_RETRIES     = 3    # number of automatic retries on transient failures
RETRY_BACKOFF   = 1.5  # exponential back-off factor (1.5s, 3s, 4.5s …)
SEARCH_CONNECT_TIMEOUT = 3
SEARCH_READ_TIMEOUT = 9
SEARCH_MAX_RETRIES = 0

ASIN_PATH_PATTERNS = (
    r"/(?:dp|gp/product|gp/aw/d|gp/aw/dp|gp/-/product|gp/offer-listing|product-reviews|review/product)/([A-Z0-9]{10})(?:[/?]|$)",
    r"/(?:o|exec/obidos)/(?:ASIN|tg/detail/-)/([A-Z0-9]{10})(?:[/?]|$)",
)

ASIN_QUERY_KEYS = ("asin", "ASIN", "pd_rd_i", "creativeASIN")


def _make_session(max_retries: int = MAX_RETRIES) -> requests.Session:
    """
    Build a requests.Session with automatic retry on connection/read errors.
    Retries are applied to the underlying urllib3 pool; they fire BEFORE
    Python sees an exception, so they handle transient socket issues
    transparently.
    """
    if max_retries <= 0:
        adapter = HTTPAdapter(max_retries=0)
    else:
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _extract_asin_from_text(text: str) -> str | None:
    for pattern in ASIN_PATH_PATTERNS:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


class AmazonCanopyAdapter(MarketplaceAdapter):
    name = "amazon"

    def can_handle_url(self, url: str) -> bool:
        hostname = (urlparse(url or "").netloc or "").lower()
        return "amazon." in hostname or "amzn." in hostname

    def extract_listing_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        decoded_url = unquote(url or "")
        decoded_path = unquote(parsed.path or "")

        for candidate in (url, decoded_url, parsed.path, decoded_path):
            asin = _extract_asin_from_text(candidate)
            if asin:
                return asin

        query_params = parse_qs(parsed.query or "")
        for key in ASIN_QUERY_KEYS:
            for value in query_params.get(key, []):
                if re.fullmatch(r"[A-Z0-9]{10}", value or "", re.IGNORECASE):
                    return value.upper()
                asin = _extract_asin_from_text(unquote(value or ""))
                if asin:
                    return asin

        for value_list in query_params.values():
            for value in value_list:
                decoded_value = unquote(value or "")
                asin = _extract_asin_from_text(decoded_value)
                if asin:
                    return asin
                if re.fullmatch(r"[A-Z0-9]{10}", decoded_value, re.IGNORECASE):
                    return decoded_value.upper()

        for segment in re.split(r"[/?]", decoded_path):
            if re.fullmatch(r"[A-Z0-9]{10}", segment or "", re.IGNORECASE):
                return segment.upper()

        return None

    def product_url(self, listing_id: str) -> str:
        return f"https://www.amazon.com/dp/{listing_id}"

    def fetch_product_profile(self, listing_id: str) -> dict:
        print(f"[Canopy] Fetching full profile for ASIN: {listing_id}")

        product = self._get_product_data(listing_id)

        if not product:
            return {
                "asin": listing_id,
                "brand": "",
                "product": {},
                "reviews": [],
                "error": "Failed to fetch product data from Canopy",
            }

        cleaned_reviews = self._normalize_reviews(product)

        return {
            "asin": listing_id,
            "brand": product.get("brand", ""),
            "product": product,
            "reviews": cleaned_reviews,
        }

    def search_similar_products(self, search_term: str) -> list:
        query = """
        query SearchProducts($input: AmazonProductSearchResultsInput!) {
        amazonProductSearchResults(input: $input) {
            productResults(input: { page: 1 }) {
            results {
                title
                asin
                brand
                rating
                ratingsTotal
                mainImageUrl
                isPrime
                price {
                display
                value
                }
            }
            }
        }
        }
        """

        search_input = {
            "searchTerm": search_term,
            "domain": "US",
        }

        if BUDGET_MIN is not None or BUDGET_MAX is not None:
            price_range = {}
            if BUDGET_MIN is not None:
                price_range["min"] = BUDGET_MIN
            if BUDGET_MAX is not None:
                price_range["max"] = BUDGET_MAX
            search_input["refinements"] = {"priceRange": price_range}

        payload = {
            "query": query,
            "variables": {"input": search_input},
        }

        session = _make_session(max_retries=SEARCH_MAX_RETRIES)
        try:
            response = session.post(
                CANOPY_URL,
                json=payload,
                headers=HEADERS,
                timeout=(SEARCH_CONNECT_TIMEOUT, SEARCH_READ_TIMEOUT),
            )
        except requests.exceptions.Timeout:
            print(f"[Canopy] Search timed out for term: '{search_term}'")
            return []
        except requests.exceptions.RequestException as exc:
            print(f"[Canopy] Search request failed: {exc}")
            return []
        finally:
            session.close()

        if response.status_code == 200:
            data = response.json()
            results = data.get("data", {}).get("amazonProductSearchResults") or {}
            product_results = results.get("productResults") or {}
            items = product_results.get("results") or []
            return [item for item in items if isinstance(item, dict)]

        print(f"[Canopy] Search failed: {response.status_code}")
        return []

    def _get_product_data(self, asin: str) -> dict:
        query = """
        query amazonProduct($asin: String!) {
          amazonProduct(input: {asin: $asin}) {
            title
            mainImageUrl
            rating
            ratingsTotal
            brand
            price {
              display
              value
            }
            featureBullets
            topReviews {
              title
              body
              rating
              verifiedPurchase
            }
            reviewsPaginated {
              reviews {
                title
                body
                rating
                verifiedPurchase
              }
            }
          }
        }
        """

        payload = {
            "query": query,
            "variables": {"asin": asin},
        }

        session = _make_session()
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 2):  # +2: 1-indexed + one extra attempt beyond retry count
            try:
                print(f"[Canopy] Product fetch attempt {attempt} for ASIN {asin}")
                response = session.post(
                    CANOPY_URL,
                    json=payload,
                    headers=HEADERS,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("errors"):
                        print(f"[Canopy] GraphQL errors: {data.get('errors')}")
                    result = data.get("data", {}).get("amazonProduct", {})
                    if result:
                        return result
                    # GraphQL returned null for the product — no point retrying
                    print(f"[Canopy] No product data returned for ASIN {asin}")
                    return {}

                print(f"[Canopy] HTTP {response.status_code} on attempt {attempt}")
                last_exc = None  # HTTP error, not an exception

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                print(f"[Canopy] Attempt {attempt} failed ({type(exc).__name__}): {exc}")

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                print(f"[Canopy] Attempt {attempt} failed ({type(exc).__name__}): {exc}")
                break  # Non-retriable error (e.g. invalid URL)

            if attempt <= MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"[Canopy] Waiting {wait:.1f}s before retry…")
                time.sleep(wait)

        if last_exc:
            print(f"[Canopy] All attempts exhausted. Last error: {last_exc}")
        else:
            print(f"[Canopy] All attempts exhausted without a valid response.")

        session.close()
        return {}

    def _normalize_reviews(self, product: dict) -> list[dict]:
        reviews = []
        reviews.extend(product.get("topReviews") or [])

        paginated = product.get("reviewsPaginated") or {}
        if isinstance(paginated, dict):
            reviews.extend(paginated.get("reviews") or [])

        reviews.extend(product.get("reviews") or [])
        cleaned_reviews = []

        for review in reviews:
            if not isinstance(review, dict):
                continue

            body = unescape(review.get("body") or review.get("text") or "").strip()
            if not body:
                continue

            cleaned_reviews.append({
                "title": unescape(review.get("title") or "").strip(),
                "body": body,
                "rating": review.get("rating", 3),
                "verifiedPurchase": review.get("verifiedPurchase", False),
            })

        return cleaned_reviews
    
    def test_canopy_connection(self):
        """Test if Canopy API is reachable and key works"""
        test_query = """
        query {
          __typename
        }
        """

        session = _make_session()
        try:
            response = session.post(
                CANOPY_URL,
                json={"query": test_query},
                headers=HEADERS,
                timeout=(5, 10)
            )
            print(f"Canopy test response: {response.status_code}")
            if response.status_code == 200:
                print("Canopy API connection successful")
            else:
                print(f"Canopy API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Cannot reach Canopy API: {e}")
        finally:
            session.close()
