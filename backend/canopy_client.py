# canopy_client.py

import os

import requests
from dotenv import load_dotenv

from backend.budget_config import BUDGET_MIN, BUDGET_MAX

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


def get_product_reviews(asin: str, page: int = 1) -> list:
    """
    Fetches Amazon reviews for a product by ASIN.
    'page' lets you paginate through more reviews if needed.
    Returns a list of review dicts — each one has text, rating, verified status.
    """

    query = """
    query amazonProductReviews($asin: String!, $page: Int) {
      amazonProductReviews(input: {asin: $asin, page: $page}) {
        reviews {
          title           
          body            
          rating          
          date            
          verifiedPurchase 
          reviewerName    
        }
      }
    }
    """

    variables = {
        "asin": asin,
        "page": page,   # Canopy returns ~10 reviews per page
    }

    payload = {"query": query, "variables": variables}

    response = requests.post(CANOPY_URL, json=payload, headers=HEADERS)

    if response.status_code == 200:
        data = response.json()
        # Drill into the nested response to just return the reviews list
        reviews_data = data.get("data", {}).get("amazonProductReviews", {})
        return reviews_data.get("reviews", [])  # returns [] if no reviews found
    else:
        print(f"[Canopy] Reviews fetch failed: {response.status_code}")
        return []


def get_full_product_profile(asin: str) -> dict:
    """
    Master function — calls both above functions and combines the results.
    This is what your FastAPI POST /analyze endpoint will call.
    Returns one clean dict with everything Nectar needs for all 7 modules.
    """

    print(f"[Canopy] Fetching full profile for ASIN: {asin}")

    product = get_product_data(asin)    # core product info
    reviews = get_product_reviews(asin) # list of review objects
    top_reviews = product.pop("topReviews", [])  # pull topReviews out of product dict

    # Merge paginated reviews + Amazon's curated topReviews for better star spread
    # Use a set to avoid duplicates by review title
    seen_titles = set()
    combined_reviews = []
    for r in (top_reviews + reviews):
        title = r.get("title", "")
        if title not in seen_titles:
            seen_titles.add(title)
            combined_reviews.append(r)
    
    # Combine into one unified response object
    # Your analysis functions (VADER, pandas, etc.) will receive this
    return {
        "asin": asin,
        "brand": product.get("brand",""),
        "product": product,   # title, price, rating, brand, features
        "reviews": reviews,   # list of individual review dicts
    }

# In canopy_client.py

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