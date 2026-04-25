# brand_reputation.py

import os
import re
import time
import requests

from .nlp_utils import extract_keywords, sia, STOP_WORDS

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

_brand_cache: dict[str, tuple[dict, float]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_get(brand_name: str) -> dict | None:
    key = brand_name.lower().strip()
    entry = _brand_cache.get(key)
    if entry and time.time() - entry[1] < CACHE_TTL_SECONDS:
        print(f"[Reputation] Cache hit for '{brand_name}' (expires in "
              f"{int(CACHE_TTL_SECONDS - (time.time() - entry[1]))}s)")
        return entry[0]
    return None


def _cache_set(brand_name: str, result: dict) -> None:
    _brand_cache[brand_name.lower().strip()] = (result, time.time())


# Domain-specific word lists

BRAND_NOISE_WORDS = {
    "also", "like", "just", "really", "very", "good", "great", "nice", "love",
    "product", "item", "thing", "would", "could", "even", "much", "well",
    "still", "used", "using", "came", "come", "said", "make", "made", "best",
    "ever", "back", "because", "dont", "didnt", "this", "that", "with", "have",
    "been", "than", "them", "they", "from", "tried", "whilst", "available",
    "getting", "going", "think", "know", "feel", "looks", "seems", "look",
    "give", "need", "want", "does", "work", "works", "worked", "will", "shall",
    "sure", "your", "their", "about", "there", "here", "when", "then",
    "these", "those", "some", "more", "less", "over", "same", "such",
    "time", "first", "last", "next", "take", "many", "away", "down",
    "only", "into", "well", "other", "people", "after", "before",
    "protein", "sugar", "taste", "chocolate", "drink", "banana", "cream",
    "bike", "ride", "rider", "motor", "cycle", "wheel", "gear", "engine",
    "team", "market", "store", "shop", "brand", "company", "business",
    "john", "jane", "mike", "dave", "mark", "paul", "james", "david",
    "chris", "steve", "lind", "harley", "davidson", "ford", "honda",
    "star", "review", "stars", "rating", "reviewed", "reviewer",
    "bought", "purchase", "purchased", "buying", "ordered", "order",
    "amazon", "website", "online", "email", "phone", "called",
    "said", "told", "asked", "answered", "replied", "reply",
    "will", "want", "cant", "dont", "didnt", "wasnt", "isnt",
    "ever", "never", "always", "usually", "often", "sometimes",
}

BRAND_BOOST = {
    "shipping", "delivery", "delivered", "arrived", "packaging", "packaged",
    "support", "service", "response", "responsive", "helpful", "unhelpful",
    "refund", "return", "returned", "exchange", "resolved", "unresolved",
    "communication", "contacted", "ignored", "delayed", "fast", "slow",
    "damaged", "broken", "missing", "wrong", "correct", "accurate",
    "trustworthy", "reliable", "unreliable", "scam", "legitimate", "fake",
    "customer", "experience", "received", "waiting", "quality",
}

BRAND_BIGRAMS = {
    "customer service", "customer support", "customer care",
    "fast delivery",    "fast shipping",    "slow delivery",   "delayed delivery",
    "never arrived",    "arrived damaged",  "wrong item",      "missing item",
    "easy return",      "return process",   "refused refund",  "full refund",
    "highly recommend", "would recommend",  "not recommend",
    "great experience", "terrible experience", "awful experience",
    "good communication", "no response",    "quick response",
    "well packaged",    "poorly packaged",  "damaged packaging",
    "money back",       "waste money",      "good value",      "great value",
    "never again",      "will return",      "repeat customer",
    "exceeded expectations", "below expectations",
    "not worth",        "not good",         "not great",
}


def extract_common_keywords(reviews: list, top_n: int = 10) -> list:
    """Thin wrapper so callers keep the same API as before."""
    return extract_keywords(
        reviews,
        field="text",
        noise_words=BRAND_NOISE_WORDS,
        boost_words=BRAND_BOOST,
        curated_bigrams=BRAND_BIGRAMS,
        min_doc_freq=3,
        min_word_length=5,
        use_proper_noun_filter=True, 
        top_n=top_n,
    )


# Brand name normalisation helpers

def normalize_brand(brand: str) -> str:
    if not brand:
        return ""
    brand = brand.strip()
    for noise in ("store", "official", "shop"):
        brand = re.sub(rf"\b{noise}\b", "", brand, flags=re.IGNORECASE)
    brand = re.sub(r"\bamazon(\.com)?\b", "", brand, flags=re.IGNORECASE)
    brand = brand.replace("&", " and ")
    brand = re.sub(r"[^a-zA-Z0-9\s\-']", " ", brand)
    return re.sub(r"\s+", " ", brand).strip()


def guess_domain(brand: str) -> str:
    clean = re.sub(r"[^a-z0-9]", "", normalize_brand(brand).lower())
    return f"{clean}.com" if clean else ""


def get_brand_candidates(brand: str) -> list[str]:
    cleaned  = normalize_brand(brand)
    no_space = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    domain   = guess_domain(cleaned)
    seen:    set[str] = set()
    result:  list[str] = []
    for c in [cleaned, brand.strip(), no_space, domain]:
        k = (c or "").strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            result.append(k)
    return result


def fuzzy_match(a: str, b: str) -> bool:
    a2 = re.sub(r"[^a-z0-9]", "", a.lower())
    b2 = re.sub(r"[^a-z0-9]", "", b.lower())
    return bool(a2 and b2 and (a2 == b2 or a2 in b2 or b2 in a2))

# Google Places helpers

def _extract_display_name(place: dict) -> str:
    display_name = place.get("displayName")

    if isinstance(display_name, dict):
        return (display_name.get("text") or "").strip()

    if isinstance(display_name, str):
        return display_name.strip()

    return (place.get("name") or "").strip()


def _extract_review_text(review: dict) -> str:
    text = review.get("text")

    if isinstance(text, dict):
        return (text.get("text") or "").strip()

    if isinstance(text, str):
        return text.strip()

    original_text = review.get("originalText")

    if isinstance(original_text, dict):
        return (original_text.get("text") or "").strip()

    if isinstance(original_text, str):
        return original_text.strip()

    return ""


def find_google_place(brand_name: str) -> dict | None:
    if not GOOGLE_PLACES_API_KEY:
        return None

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount",
    }

    for candidate in get_brand_candidates(brand_name):
        body = {
            "textQuery": candidate,
            "pageSize": 1,
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=15)

            if resp.status_code != 200:
                print(f"[Reputation] Google Text Search error for '{candidate}': {resp.status_code} {resp.text}")
                continue

            places_found = resp.json().get("places", [])

            if places_found:
                best = places_found[0]
                print(f"[Reputation] Google matched '{_extract_display_name(best)}' for '{candidate}'")
                return best
        except Exception as e:
            print(f"[Reputation] Google Text Search error for '{candidate}': {e}")

    return None


def get_google_place_details(place_id: str) -> dict:
    if not GOOGLE_PLACES_API_KEY or not place_id:
        return {}

    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "id,displayName,rating,userRatingCount,reviews",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code != 200:
            print(f"[Reputation] Google Place Details error: {resp.status_code} {resp.text}")
            return {}

        return resp.json()
    except Exception as e:
        print(f"[Reputation] Google Place Details error: {e}")
        return {}


def normalize_google_reviews(place_details: dict) -> list[dict]:
    result = []

    for review in place_details.get("reviews", []) or []:
        text = _extract_review_text(review)

        if text:
            result.append({
                "text": text,
                "title": "",
                "rating": review.get("rating", 3),
            })

    return result


def normalize_amazon_reviews(amazon_reviews: list | None) -> list[dict]:
    if not amazon_reviews:
        return []
    result = []
    for r in amazon_reviews:
        if not isinstance(r, dict):
            continue
        text = (r.get("body") or r.get("text") or r.get("content") or "").strip()
        if text:
            result.append({
                "text":   text,
                "title":  (r.get("title") or r.get("headline") or "").strip(),
                "rating": r.get("rating", 3),
            })
    return result


# Insight + scoring 

def build_reputation_insights(
    reviews: list,
    brand_name: str,
    source_name: str = "brand_reviews",
) -> dict:
    if not reviews:
        return {
            "brand": brand_name,
            "reputation_score_pct": None,
            "overall_label": "Insufficient brand review data found.",
            "avg_compound": None,
            "positive_pct": None,
            "negative_pct": None,
            "reviews_analyzed": 0,
            "insights": [
                {"topic": "Customer Support",    "status": "Unknown"},
                {"topic": "Shipping & Delivery", "status": "Unknown"},
                {"topic": "Build Quality",       "status": "Unknown"},
            ],
            "commonKeywords": [],
            "source": source_name,
        }

    compound_scores = []
    pos = neg = neu = 0
    support_scores  = []
    shipping_scores = []
    quality_scores  = []

    for review in reviews:
        text       = review["text"]
        text_lower = text.lower()
        compound   = sia.polarity_scores(text)["compound"]
        compound_scores.append(compound)

        if compound >= 0.05:    pos += 1
        elif compound <= -0.05: neg += 1
        else:                   neu += 1

        if any(kw in text_lower for kw in ["support", "service", "help", "response", "refund", "return", "agent"]):
            support_scores.append(compound)
        if any(kw in text_lower for kw in ["shipping", "delivery", "arrived", "package", "delayed", "late", "fast", "slow"]):
            shipping_scores.append(compound)
        if any(kw in text_lower for kw in ["quality", "durable", "broke", "build", "material", "lasted", "cheap", "premium"]):
            quality_scores.append(compound)

    total        = len(compound_scores)
    avg_compound = sum(compound_scores) / total if total else 0

    def _status(scores: list) -> str:
        if not scores: return "Neutral"
        m = sum(scores) / len(scores)
        return "Positive" if m >= 0.05 else "Caution" if m <= -0.05 else "Neutral"

    insights = [
        {"topic": "Customer Support",    "status": _status(support_scores)},
        {"topic": "Shipping & Delivery", "status": _status(shipping_scores)},
        {"topic": "Build Quality",       "status": _status(quality_scores)},
    ]

    avg_rating     = sum(float(r.get("rating", 3) or 3) for r in reviews) / total if total else 3
    sentiment_pct  = ((avg_compound + 1) / 2) * 100
    rating_pct     = (avg_rating / 5) * 100
    rep_score      = round((sentiment_pct * 0.45) + (rating_pct * 0.55)) if total else None

    if   rep_score >= 80: label = "Strong overall brand reputation."
    elif rep_score >= 65: label = "Mostly positive brand reputation with some concerns."
    elif rep_score >= 50: label = "Mixed brand reputation."
    else:                 label = "Weak brand reputation based on available reviews."

    return {
        "brand":                brand_name,
        "reputation_score_pct": rep_score,
        "overall_label":        label,
        "avg_compound":         round(avg_compound, 3),
        "positive_pct":         round((pos / total) * 100) if total else 0,
        "negative_pct":         round((neg / total) * 100) if total else 0,
        "reviews_analyzed":     total,
        "insights":             insights,
        "commonKeywords":       extract_common_keywords(reviews),
        "source":               source_name,
    }


async def get_brand_reputation(
    brand_name: str,
    amazon_reviews: list | None = None,
) -> dict:
    print(f"\n[Reputation] Analyzing brand: '{brand_name}'")

    cached = _cache_get(brand_name)
    if cached is not None:
        return cached

    google_reviews: list[dict] = []
    place = find_google_place(brand_name) if GOOGLE_PLACES_API_KEY else None
    if place:
        details = get_google_place_details(place.get("id", ""))
        google_reviews = normalize_google_reviews(details)
        print(f"[Reputation] Google reviews found: {len(google_reviews)}")
    else:
        print("[Reputation] No Google place match or API key missing")

    amazon_normalized = normalize_amazon_reviews(amazon_reviews)
    print(f"[Reputation] Amazon fallback reviews: {len(amazon_normalized)}")

    if len(google_reviews) >= 3:
        result = build_reputation_insights(google_reviews, brand_name, "google_places")
    elif amazon_normalized:
        result = build_reputation_insights(amazon_normalized, brand_name, "amazon_reviews_fallback")
    elif google_reviews:
        result = build_reputation_insights(google_reviews, brand_name, "google_places_limited")
    else:
        result = {
            "brand": brand_name,
            "reputation_score_pct": None,
            "overall_label": "Brand review data unavailable.",
            "avg_compound": None,
            "positive_pct": None,
            "negative_pct": None,
            "reviews_analyzed": 0,
            "insights": [
                {"topic": "Customer Support",    "status": "Unknown"},
                {"topic": "Shipping & Delivery", "status": "Unknown"},
                {"topic": "Build Quality",       "status": "Unknown"},
            ],
            "commonKeywords": [],
            "source": "no_brand_review_source_available",
        }

    # Store in cache before returning
    _cache_set(brand_name, result)
    return result