# brand_reputation.py

import re
import requests                                      # sends HTTP requests to Trustpilot
import json                                          # parses the JSON blob embedded in Trustpilot's HTML
import time                                          # polite delay between page requests
from collections import Counter                      # counts word frequencies for commonKeywords
from bs4 import BeautifulSoup                        # parses the HTML page structure
import nltk
nltk.download('vader_lexicon', quiet=True)
nltk.download('stopwords', quiet=True)
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.corpus import stopwords

sia = SentimentIntensityAnalyzer()                   # one shared VADER instance

STOP_WORDS = set(stopwords.words('english'))         # common words to exclude from keyword counts

# Browser-like headers so Trustpilot doesn't immediately block the request
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def normalize_brand(brand: str) -> str:
    if not brand:
        return ""
    brand = brand.lower().strip()
    brand = re.sub(r"[^a-z0-9 ]", "", brand)
    brand = re.sub(r"\s+", " ", brand)
    return brand


def guess_domain(brand: str) -> str:
    if not brand:
        return ""
    clean = re.sub(r"[^a-z0-9]", "", brand.lower())
    return f"{clean}.com"


def get_trustpilot_candidates(brand: str):
    """
    Generates multiple ways Trustpilot might recognize a company.
    """
    return [
        brand,
        normalize_brand(brand),
        brand.replace(" ", ""),
        guess_domain(brand),
    ]

def find_trustpilot_slug(brand_name: str) -> str | None:
    brand_name = brand_name.strip()
    search_url = f"https://www.trustpilot.com/search?query={brand_name.replace(' ', '+')}"

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            print(f"[Trustpilot] Search returned status {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if not next_data_tag:
            print("[Trustpilot] __NEXT_DATA__ not found")
            return None

        page_data = json.loads(next_data_tag.string)

        # ✅ FIX: multiple fallback paths (Trustpilot changes structure often)
        page_props = page_data.get("props", {}).get("pageProps", {})

        business_units = (
            page_props.get("businessUnits")
            or page_props.get("businesses")
            or page_props.get("searchResults", {}).get("businessUnits")
            or page_props.get("searchResult", {}).get("businessUnits")
            or page_props.get("hits")
            or []
        )

        # NEW FALLBACK: sometimes results are nested deeper
        if not business_units and isinstance(page_props.get("pageData"), dict):
            business_units = page_props["pageData"].get("businessUnits", [])

        if not business_units:
            print(f"[Trustpilot] No businesses found for '{brand_name}'")
            return None

        first = None

        for b in business_units:
            name = (b.get("name") or "").lower()
            if brand_name.lower() in name:
                first = b
                break

        if not first:
            first = business_units[0]

        # 🔥 FIX: Trustpilot often uses "slug" OR "identifyingName"
        slug = (
            first.get("identifyingName")
            or first.get("slug")
            or first.get("name")
            or first.get("websiteUrl", "").replace("https://www.trustpilot.com/review/", "")
        )

        if slug:
            print(f"[Trustpilot] Matched slug: {slug}")
            return slug

        return None

    except Exception as e:
        print(f"[Trustpilot] Slug search error: {e}")
        return None

def scrape_trustpilot_reviews(slug: str, max_reviews: int = 20) -> list:
    """
    Scrapes review data from a Trustpilot company page using the slug.
    Fetches 2 pages (typically ~20 reviews) using the same __NEXT_DATA__ technique.
    
    Returns a list of dicts: {text, title, rating}
    Returns an empty list if scraping fails.
    """
    reviews = []

    for page_num in range(1, 3):                        # pages 1 and 2
        url = f"https://www.trustpilot.com/review/{slug}?page={page_num}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)

            if response.status_code != 200:
                print(f"[Trustpilot] Reviews page {page_num} returned {response.status_code}")
                break

            soup = BeautifulSoup(response.text, "html.parser")

            next_data_tag = soup.find("script", id="__NEXT_DATA__")
            if not next_data_tag:
                print(f"[Trustpilot] No __NEXT_DATA__ on reviews page {page_num}")
                break

            page_data = json.loads(next_data_tag.string)

            # Trustpilot stores reviews at props → pageProps → reviews
            page_reviews = (
            page_data
            .get("props", {})
            .get("pageProps", {})
            .get("reviews")
            or page_data
            .get("props", {})
            .get("reviews")
            or []
        )

            for review in page_reviews:
                text = review.get("text", "")
                title = review.get("title", "")
                rating = review.get("rating", 3)        # 1–5 star rating

                if text:                                 # skip reviews with no written content
                    reviews.append({
                        "text": text,
                        "title": title,
                        "rating": rating,
                    })

            time.sleep(1.5)                             # be polite — don't hammer the server

        except Exception as e:
            print(f"[Trustpilot] Error on page {page_num}: {e}")
            break

        if len(reviews) >= max_reviews:
            break

    return reviews[:max_reviews]

BRAND_NOISE_WORDS = {
    "also", "like", "just", "really", "very", "good", "great", "nice", "love",
    "product", "item", "thing", "would", "could", "even", "much", "well",
    "still", "used", "using", "came", "come", "said", "make", "made", "best",
    "ever", "back", "because", "dont", "didnt", "this", "that", "with", "have",
    "been", "than", "them", "they", "from", "protein", "sugar", "taste",
    "chocolate", "drink", "banana", "cream", "tried", "whilst", "available",
}

def extract_common_keywords(reviews: list, top_n: int = 10) -> list:
    word_counts = Counter()
    word_sentiments: dict[str, list[float]] = {}

    for review in reviews:
        text = review.get("text", "")
        if not text:
            continue

        compound = sia.polarity_scores(text)["compound"]
        words = re.findall(r"[a-z]{4,}", text.lower())
        unique_words = set(words)

        for word in unique_words:
            if word not in STOP_WORDS and word not in BRAND_NOISE_WORDS:
                word_counts[word] += 1
                word_sentiments.setdefault(word, []).append(compound)

    # Boost words that describe brand experience
    BRAND_BOOST = {
        "shipping", "delivery", "delivered", "arrived", "packaging", "packaged",
        "support", "service", "response", "responsive", "helpful", "unhelpful",
        "refund", "return", "returned", "exchange", "resolved", "unresolved",
        "communication", "contacted", "ignored", "delayed", "fast", "slow",
        "damaged", "broken", "missing", "wrong", "correct", "accurate",
        "trustworthy", "reliable", "unreliable", "scam", "legitimate", "fake",
        "customer", "experience", "ordered", "order", "received", "waiting",
    }

    boosted_counts = Counter()
    for word, count in word_counts.items():
        boosted_counts[word] = count * 2 if word in BRAND_BOOST else count

    keywords = []
    for word, _ in boosted_counts.most_common(top_n):
        count = word_counts[word]
        scores = word_sentiments.get(word, [])
        avg = sum(scores) / len(scores) if scores else 0

        sentiment = "positive" if avg >= 0.05 else "negative" if avg <= -0.05 else "neutral"
        keywords.append({"word": word, "count": count, "sentiment": sentiment})

    return keywords


def build_reputation_insights(reviews: list, brand_name: str) -> dict:
    """
    Runs VADER on all Trustpilot reviews and builds:
      - A headline compound score (-1.0 to +1.0)
      - A human-readable overall label
      - 3 insight bullet points for the Nectar UI
      - A percentage score for the UI bar display (0–100)
      - commonKeywords: top words from reviews with sentiment label
    """
    if not reviews:
        # Return a neutral fallback so the pipeline doesn't crash
        return {
            "brand": brand_name,
            "reputation_score_pct": None,
            "overall_label": "Insufficient Trustpilot data found for this brand.",
            "insights": [
                {"topic": "Customer Satisfaction", "status": "N/A"},
                {"topic": "Review Sentiment",       "status": "N/A"},
                {"topic": "Overall Brand Trust",    "status": "N/A"},
            ],
            "commonKeywords": [],
            "reviews_analyzed": 0,
        }

    compound_scores = []
    pos_count = neg_count = neu_count = 0

    # Keyword lists for specific insight topics — same approach as reddit_reputation.py
    support_texts = []
    shipping_texts = []
    quality_texts = []

    for review in reviews:
        text = review["text"]
        text_lower = text.lower()

        compound = sia.polarity_scores(text)["compound"]   # VADER score: -1 to +1
        compound_scores.append(compound)

        # Tally sentiment labels
        if compound >= 0.05:
            pos_count += 1
        elif compound <= -0.05:
            neg_count += 1
        else:
            neu_count += 1

        # Route this review text into topic buckets based on keywords
        # Each bucket is later scored separately for the 3 bullet points
        if any(kw in text_lower for kw in ["support", "service", "help", "response", "refund", "return", "agent"]):
            support_texts.append(compound)

        if any(kw in text_lower for kw in ["shipping", "delivery", "arrived", "package", "delayed", "late", "fast", "slow"]):
            shipping_texts.append(compound)

        if any(kw in text_lower for kw in ["quality", "durable", "broke", "build", "material", "lasted", "cheap", "premium"]):
            quality_texts.append(compound)

    total = len(compound_scores)
    avg_compound = sum(compound_scores) / total if total > 0 else 0            # overall average: -1.0 to +1.0

    def scores_to_status(scores: list) -> str:
        """
        Given a list of compound scores for a topic,
        returns 'Positive', 'Caution', or 'Neutral' for the UI badge.
        Falls back to 'Neutral' if no reviews mentioned this topic.
        """
        if not scores:
            return "Neutral"                               # not enough data on this topic
        mean = sum(scores) / len(scores)
        if mean >= 0.05:
            return "Positive"
        elif mean <= -0.05:
            return "Caution"
        else:
            return "Neutral"

    # Build the 3 bullet points — maps directly to Nectar's Reputation Insights panel
    insights = [
        {"topic": "Customer Support",    "status": scores_to_status(support_texts)},
        {"topic": "Shipping & Delivery", "status": scores_to_status(shipping_texts)},
        {"topic": "Build Quality",       "status": scores_to_status(quality_texts)},
    ]

    # Convert compound score (-1 to +1) → 0–100 percentage for the UI progress bar
    avg_rating = sum(review.get("rating", 3) for review in reviews) / total if total > 0 else 3

    sentiment_score = ((avg_compound + 1) / 2) * 100
    rating_score = (avg_rating / 5) * 100

    reputation_score_pct = round((sentiment_score * 0.45) + (rating_score * 0.55)) if total > 0 else None

    # Overall label shown under the score
    if reputation_score_pct >= 80:
        overall_label = "Strong overall brand reputation on Trustpilot."
    elif reputation_score_pct >= 65:
        overall_label = "Mostly positive brand reputation with some concerns."
    elif reputation_score_pct >= 50:
        overall_label = "Mixed brand reputation on Trustpilot."
    else:
        overall_label = "Weak brand reputation based on recent Trustpilot reviews."

    return {
        "brand": brand_name,
        "reputation_score_pct": reputation_score_pct,      # e.g. 72 → shown as score in UI
        "overall_label": overall_label,
        "avg_compound": round(avg_compound, 3),
        "positive_pct": round((pos_count / total) * 100) if total > 0 else 0,
        "negative_pct": round((neg_count / total) * 100) if total > 0 else 0,
        "reviews_analyzed": total,
        "insights": insights,                               # 3 bullet points for the UI
        "commonKeywords": extract_common_keywords(reviews), # top words driving the score
    }


def get_brand_reputation(brand_name: str) -> dict:
    """
    Master function — the one your FastAPI /analyze endpoint calls.
    Takes brand_name (now auto-extracted from Canopy's 'brand' field),
    finds the Trustpilot page, scrapes reviews, runs VADER, returns report.
    """
    print(f"\n[Reputation] Analyzing brand: '{brand_name}'")

    slug = find_trustpilot_slug(brand_name)             # step 1: find the company's Trustpilot URL

    if not slug:
        print(f"[Reputation] No Trustpilot slug found — returning neutral fallback")
        return {
            "brand": brand_name,
            "reputation_score_pct": None,
            "overall_label": "Trustpilot data unavailable — fallback required",
            "avg_compound": None,
            "positive_pct": None,
            "negative_pct": None,
            "reviews_analyzed": 0,
            "insights": [
                {"topic": "Customer Support", "status": "Unknown"},
                {"topic": "Shipping & Delivery", "status": "Unknown"},
                {"topic": "Build Quality", "status": "Unknown"},
            ],
            "commonKeywords": [],
            "source": "no_trustpilot_data"
        } 

    reviews = scrape_trustpilot_reviews(slug)           # step 2: scrape up to 20 reviews
    return build_reputation_insights(reviews, brand_name)  # step 3: VADER + build report