# canopy_client.py

import os

import requests
from dotenv import load_dotenv

from .budget_config import BUDGET_MIN, BUDGET_MAX

load_dotenv()

API_KEY = os.getenv("CANOPY_API_KEY")
CANOPY_URL = "https://graphql.canopyapi.co/"

if not API_KEY:
    raise RuntimeError("Missing CANOPY_API_KEY environment variable.")

HEADERS = {
    "Content-Type": "application/json",
    "API-KEY": API_KEY,
}
### REMINDER : NEED TO IMPLEMENT Trustpilot (BRAND REPUTATION)

def get_product_data(asin: str) -> dict:
    """
    Fetches core product info from Amazon via Canopy.
    'asin' is Amazon's unique product ID (e.g. 'B0B3JBVDYP').
    You'll get this from your CLIP/OCR pipeline identifying the product.
    """

    # GraphQL query — think of this like a SQL SELECT statement
    # We're asking Canopy: give me these specific fields for this product
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
      }
    }
    """

    # Variables are passed separately from the query string
    # This is safer and cleaner than string formatting the ASIN directly into the query
    variables = {"asin": asin}

    # "payload" is everything we send in the POST request body
    payload = {
        "query": query,
        "variables": variables,
    }

    # Send the POST request — json=payload auto-converts our dict to JSON string
    response = requests.post(CANOPY_URL, json=payload, headers=HEADERS)

    # 200 means the server responded successfully
    if response.status_code == 200:
        data = response.json()  # parse the JSON response body into a Python dict

        # GraphQL always nests results under "data" — then the query name
        return data.get("data", {}).get("amazonProduct", {})
    else:
        # Log the failure but don't crash the whole app
        print(f"[Canopy] Product fetch failed: {response.status_code}")
        print(f"[Canopy] Response: {response.text}")
        return {}


def get_full_product_profile(asin: str) -> dict:
    print(f"[Canopy] Fetching full profile for ASIN: {asin}")

    product = get_product_data(asin)

    if not product:
        return {
            "asin": asin,
            "brand": "",
            "product": {},
            "reviews": [],
            "error": "Failed to fetch product data from Canopy"
        }

    top_reviews = product.get("topReviews", [])

    cleaned_reviews = [
        {
            "title": r.get("title", ""),
            "body": r.get("body", ""),
            "rating": r.get("rating", 3),
            "verifiedPurchase": r.get("verifiedPurchase", False),
        }
        for r in top_reviews
        if r.get("body")  # skip empty reviews
    ]

    return {
        "asin": asin,
        "brand": product.get("brand", ""),
        "product": product,
        "reviews": cleaned_reviews,
    }

def search_similar_products(search_term: str) -> list:
    """
    Searches Amazon for products matching the search term,
    filtered to the budget range defined in budget_config.py.
    BUDGET_MIN and BUDGET_MAX can be changed at any time in that file.
    """

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

    # Build the input — only add priceRange if at least one bound is set
    search_input = {
        "searchTerm": search_term,
        "domain": "US"
    }

    # Only attach refinements block if we actually have a budget set
    if BUDGET_MIN is not None or BUDGET_MAX is not None:
        price_range = {}
        if BUDGET_MIN is not None:
            price_range["min"] = BUDGET_MIN     # e.g. 20.00
        if BUDGET_MAX is not None:
            price_range["max"] = BUDGET_MAX     # e.g. 200.00
        search_input["refinements"] = {"priceRange": price_range}

    variables = {"input": search_input}
    payload = {"query": query, "variables": variables}
    response = requests.post(CANOPY_URL, json=payload, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()
        results = data.get("data", {}).get("amazonProductSearchResults", {})
        return results.get("productResults", {}).get("results", [])
    else:
        print(f"[Canopy] Search failed: {response.status_code}")
        return []