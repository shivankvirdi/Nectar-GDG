import os
import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests
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

ASIN_PATH_PATTERNS = (
    r"/(?:dp|gp/product|gp/aw/d|gp/aw/dp|gp/-/product|gp/offer-listing|product-reviews|review/product)/([A-Z0-9]{10})(?:[/?]|$)",
    r"/(?:o|exec/obidos)/(?:ASIN|tg/detail/-)/([A-Z0-9]{10})(?:[/?]|$)",
)

ASIN_QUERY_KEYS = ("asin", "ASIN", "pd_rd_i", "creativeASIN")


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
            productResults(input: { page: 1, sort: AVERAGE_CUSTOMER_REVIEW }) {
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
                featureBullets
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
        response = requests.post(CANOPY_URL, json=payload, headers=HEADERS)

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
        try:
            response = requests.post(CANOPY_URL, json=payload, headers=HEADERS, timeout=20)
        except requests.RequestException as exc:
            print(f"[Canopy] Product fetch failed: {exc}")
            return {}

        if response.status_code == 200:
            data = response.json()
            if data.get("errors"):
                print(f"[Canopy] Product fetch returned GraphQL errors: {data.get('errors')}")
            return data.get("data", {}).get("amazonProduct", {})

        print(f"[Canopy] Product fetch failed: {response.status_code}")
        print(f"[Canopy] Response: {response.text}")
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
