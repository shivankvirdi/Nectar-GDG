import os
import re
import math
import requests
from collections import Counter
from urllib.parse import quote_plus

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize
from nltk.stem import WordNetLemmatizer

nltk.download("vader_lexicon", quiet=True)
nltk.download("stopwords", quiet=True)
nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("wordnet", quiet=True)
nltk.download("averaged_perceptron_tagger", quiet=True)

sia = SentimentIntensityAnalyzer()
lemmatizer = WordNetLemmatizer()
STOP_WORDS = set(stopwords.words("english"))

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


# ─── Brand helpers ────────────────────────────────────────────────────────────

def normalize_brand(brand: str) -> str:
    if not brand:
        return ""

    brand = brand.strip()
    brand = re.sub(r"\bstore\b", "", brand, flags=re.IGNORECASE)
    brand = re.sub(r"\bofficial\b", "", brand, flags=re.IGNORECASE)
    brand = re.sub(r"\bshop\b", "", brand, flags=re.IGNORECASE)
    brand = re.sub(r"\bamazon\b", "", brand, flags=re.IGNORECASE)
    brand = re.sub(r"\bamazon\.com\b", "", brand, flags=re.IGNORECASE)
    brand = brand.replace("&", " and ")
    brand = re.sub(r"[^a-zA-Z0-9\s\-']", " ", brand)
    brand = re.sub(r"\s+", " ", brand).strip()
    return brand


def normalize_brand_basic(brand: str) -> str:
    if not brand:
        return ""
    brand = brand.lower().strip()
    brand = re.sub(r"[^a-z0-9 ]", "", brand)
    return re.sub(r"\s+", " ", brand)


def guess_domain(brand: str) -> str:
    if not brand:
        return ""
    clean = re.sub(r"[^a-z0-9]", "", normalize_brand(brand).lower())
    return f"{clean}.com" if clean else ""


def get_brand_candidates(brand: str) -> list[str]:
    cleaned = normalize_brand(brand)
    basic = normalize_brand_basic(cleaned)
    no_space = basic.replace(" ", "")
    domain = guess_domain(cleaned)

    candidates = [
        cleaned,
        basic,
        no_space,
        domain,
        brand.strip() if brand else "",
    ]

    final = []
    seen = set()
    for candidate in candidates:
        c = (candidate or "").strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            final.append(c)

    return final


def simplify_for_match(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def fuzzy_match(a: str, b: str) -> bool:
    a_simple = simplify_for_match(a)
    b_simple = simplify_for_match(b)
    if not a_simple or not b_simple:
        return False
    return a_simple == b_simple or a_simple in b_simple or b_simple in a_simple


# ─── Google Places helpers ────────────────────────────────────────────────────

def find_google_place(brand_name: str) -> dict | None:
    if not GOOGLE_PLACES_API_KEY:
        return None

    candidates = get_brand_candidates(brand_name)
    print(f"[Brand Reputation] Google candidates: {candidates}")

    for candidate in candidates:
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": candidate,
            "inputtype": "textquery",
            "fields": "place_id,name,rating,user_ratings_total",
            "key": GOOGLE_PLACES_API_KEY,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code != 200:
                print(f"[Brand Reputation] Google Find Place returned {response.status_code} for '{candidate}'")
                continue

            data = response.json()
            candidates_found = data.get("candidates", [])
            if not candidates_found:
                continue

            best = candidates_found[0]
            print(f"[Brand Reputation] Google matched place '{best.get('name', '')}' for '{candidate}'")
            return best

        except Exception as e:
            print(f"[Brand Reputation] Google Find Place error for '{candidate}': {e}")

    return None


def get_google_place_details(place_id: str) -> dict:
    if not GOOGLE_PLACES_API_KEY or not place_id:
        return {}

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,rating,user_ratings_total,reviews",
        "reviews_sort": "most_relevant",
        "key": GOOGLE_PLACES_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            print(f"[Brand Reputation] Google Place Details returned {response.status_code}")
            return {}

        data = response.json()
        return data.get("result", {}) or {}

    except Exception as e:
        print(f"[Brand Reputation] Google Place Details error: {e}")
        return {}


def normalize_google_reviews(place_details: dict) -> list[dict]:
    normalized = []

    for review in place_details.get("reviews", []) or []:
        text = (review.get("text") or "").strip()
        if not text:
            continue

        rating = review.get("rating", 3)
        title = ""

        normalized.append({
            "text": text,
            "title": title,
            "rating": rating,
        })

    return normalized


def normalize_amazon_reviews(amazon_reviews: list | None) -> list[dict]:
    if not amazon_reviews:
        return []

    normalized = []

    for review in amazon_reviews:
        if not isinstance(review, dict):
            continue

        text = (
            review.get("body")
            or review.get("text")
            or review.get("content")
            or ""
        ).strip()

        if not text:
            continue

        rating = review.get("rating", 3)
        title = (review.get("title") or review.get("headline") or "").strip()

        normalized.append({
            "text": text,
            "title": title,
            "rating": rating,
        })

    return normalized


# ─── Keyword config ───────────────────────────────────────────────────────────

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
    "fast delivery", "fast shipping", "slow delivery", "delayed delivery",
    "never arrived", "arrived damaged", "wrong item", "missing item",
    "easy return", "return process", "refused refund", "full refund",
    "highly recommend", "would recommend", "not recommend",
    "great experience", "terrible experience", "awful experience",
    "good communication", "no response", "quick response",
    "well packaged", "poorly packaged", "damaged packaging",
    "money back", "waste money", "good value", "great value",
    "never again", "will return", "repeat customer",
    "exceeded expectations", "below expectations",
    "not worth", "not good", "not great",
}

NEGATION_WORDS = {
    "not", "no", "never", "cant", "cannot", "wont", "dont",
    "doesnt", "didnt", "isnt", "wasnt", "barely", "hardly",
    "scarcely", "nothing", "neither",
}

MIN_WORD_LENGTH = 5
MIN_DOC_FREQ = 3


# ─── Keyword extraction helpers ───────────────────────────────────────────────

def _build_proper_noun_set(reviews: list, field: str = "text") -> set[str]:
    cap_count: Counter = Counter()
    total_count: Counter = Counter()

    for review in reviews:
        text = review.get(field, "") or ""
        try:
            sentences = sent_tokenize(text)
        except Exception:
            sentences = text.split(".")

        for sent in sentences:
            tokens = sent.split()
            for i, tok in enumerate(tokens):
                clean = re.sub(r"[^a-zA-Z]", "", tok).lower()
                if len(clean) < MIN_WORD_LENGTH:
                    continue
                total_count[clean] += 1
                if i > 0 and tok and tok[0].isupper():
                    cap_count[clean] += 1

    proper_nouns = set()
    for word, total in total_count.items():
        if total >= 2 and cap_count[word] / total > 0.6:
            proper_nouns.add(word)

    return proper_nouns


def _lemma(word: str) -> str:
    return lemmatizer.lemmatize(word.lower())


def _sentence_scores_for_term(term: str, reviews: list, field: str) -> list[float]:
    scores = []
    pat = re.compile(re.escape(term), re.IGNORECASE)

    for review in reviews:
        text = review.get(field, "") or ""
        try:
            sentences = sent_tokenize(text)
        except Exception:
            sentences = text.split(".")

        for sent in sentences:
            if pat.search(sent):
                scores.append(sia.polarity_scores(sent)["compound"])

    return scores


def _negation_bigrams(text: str) -> list[str]:
    tokens = re.findall(r"[a-z']+", text.lower())
    pairs = []

    for i, tok in enumerate(tokens[:-1]):
        if tok.replace("'", "") in NEGATION_WORDS:
            nxt = tokens[i + 1]
            if (
                len(nxt) >= MIN_WORD_LENGTH
                and nxt not in STOP_WORDS
                and nxt not in BRAND_NOISE_WORDS
            ):
                pairs.append(f"not {_lemma(nxt)}")

    return pairs


def extract_common_keywords(reviews: list, top_n: int = 10) -> list:
    total = len(reviews)
    if total == 0:
        return []

    proper_nouns = _build_proper_noun_set(reviews, field="text")
    print(f"[Keywords] Proper nouns detected and blocked: {proper_nouns}")

    word_counts: Counter = Counter()
    word_doc_freq: Counter = Counter()
    bigram_counts: Counter = Counter()
    bigram_doc_freq: Counter = Counter()
    negation_counts: Counter = Counter()

    for review in reviews:
        text = review.get("text", "") or ""
        if not text:
            continue

        text_lower = text.lower()
        raw_words = re.findall(r"[a-z]{%d,}" % MIN_WORD_LENGTH, text_lower)
        seen_lemmas: set[str] = set()

        for w in raw_words:
            lemma = _lemma(w)
            if (
                lemma not in STOP_WORDS
                and lemma not in BRAND_NOISE_WORDS
                and lemma not in proper_nouns
                and len(lemma) >= MIN_WORD_LENGTH
            ):
                word_counts[lemma] += 1
                if lemma not in seen_lemmas:
                    word_doc_freq[lemma] += 1
                    seen_lemmas.add(lemma)

        seen_bg: set[str] = set()
        for bg in BRAND_BIGRAMS:
            if bg in text_lower:
                bigram_counts[bg] += 1
                if bg not in seen_bg:
                    bigram_doc_freq[bg] += 1
                    seen_bg.add(bg)

        for neg in _negation_bigrams(text):
            negation_counts[neg] += 1

    def idf(df: int) -> float:
        return math.log(total / (1 + df)) + 1.0

    scored: dict[str, float] = {}

    for lemma, count in word_counts.items():
        df = word_doc_freq[lemma]
        if df < MIN_DOC_FREQ:
            continue
        boost = 2.0 if lemma in BRAND_BOOST else 1.0
        scored[lemma] = count * idf(df) * boost

    for bg, count in bigram_counts.items():
        df = bigram_doc_freq[bg]
        if df < MIN_DOC_FREQ:
            continue
        scored[bg] = count * idf(df) * 3.0

    for neg, count in negation_counts.items():
        if count >= MIN_DOC_FREQ:
            scored[neg] = count * 4.0

    top_terms = sorted(scored, key=scored.__getitem__, reverse=True)[:top_n]

    keywords = []
    for term in top_terms:
        is_negation = term.startswith("not ") and " " in term
        is_bigram = " " in term

        raw_count = negation_counts[term] if is_bigram and is_negation else (
            bigram_counts[term] if is_bigram else word_counts[term]
        )

        if is_negation:
            sentiment = "negative"
        else:
            sscores = _sentence_scores_for_term(term, reviews, field="text")
            avg = sum(sscores) / len(sscores) if sscores else 0.0
            sentiment = "positive" if avg >= 0.05 else "negative" if avg <= -0.05 else "neutral"

        keywords.append({
            "word": term,
            "count": raw_count,
            "sentiment": sentiment,
        })

    return keywords


# ─── Insight + scoring ────────────────────────────────────────────────────────

def build_reputation_insights(
    reviews: list,
    brand_name: str,
    source_name: str = "brand_reviews"
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
                {"topic": "Customer Support", "status": "Unknown"},
                {"topic": "Shipping & Delivery", "status": "Unknown"},
                {"topic": "Build Quality", "status": "Unknown"},
            ],
            "commonKeywords": [],
            "source": source_name,
        }

    compound_scores = []
    pos_count = neg_count = neu_count = 0
    support_texts = []
    shipping_texts = []
    quality_texts = []

    for review in reviews:
        text = review["text"]
        text_lower = text.lower()
        compound = sia.polarity_scores(text)["compound"]
        compound_scores.append(compound)

        if compound >= 0.05:
            pos_count += 1
        elif compound <= -0.05:
            neg_count += 1
        else:
            neu_count += 1

        if any(kw in text_lower for kw in ["support", "service", "help", "response", "refund", "return", "agent"]):
            support_texts.append(compound)

        if any(kw in text_lower for kw in ["shipping", "delivery", "arrived", "package", "delayed", "late", "fast", "slow"]):
            shipping_texts.append(compound)

        if any(kw in text_lower for kw in ["quality", "durable", "broke", "build", "material", "lasted", "cheap", "premium"]):
            quality_texts.append(compound)

    total = len(compound_scores)
    avg_compound = sum(compound_scores) / total if total > 0 else 0

    def scores_to_status(scores: list) -> str:
        if not scores:
            return "Neutral"
        mean = sum(scores) / len(scores)
        if mean >= 0.05:
            return "Positive"
        if mean <= -0.05:
            return "Caution"
        return "Neutral"

    insights = [
        {"topic": "Customer Support", "status": scores_to_status(support_texts)},
        {"topic": "Shipping & Delivery", "status": scores_to_status(shipping_texts)},
        {"topic": "Build Quality", "status": scores_to_status(quality_texts)},
    ]

    avg_rating = sum(float(r.get("rating", 3) or 3) for r in reviews) / total if total > 0 else 3
    sentiment_score = ((avg_compound + 1) / 2) * 100
    rating_score = (avg_rating / 5) * 100
    reputation_score_pct = round((sentiment_score * 0.45) + (rating_score * 0.55)) if total > 0 else None

    if reputation_score_pct >= 80:
        overall_label = "Strong overall brand reputation."
    elif reputation_score_pct >= 65:
        overall_label = "Mostly positive brand reputation with some concerns."
    elif reputation_score_pct >= 50:
        overall_label = "Mixed brand reputation."
    else:
        overall_label = "Weak brand reputation based on available reviews."

    return {
        "brand": brand_name,
        "reputation_score_pct": reputation_score_pct,
        "overall_label": overall_label,
        "avg_compound": round(avg_compound, 3),
        "positive_pct": round((pos_count / total) * 100) if total > 0 else 0,
        "negative_pct": round((neg_count / total) * 100) if total > 0 else 0,
        "reviews_analyzed": total,
        "insights": insights,
        "commonKeywords": extract_common_keywords(reviews),
        "source": source_name,
    }


# ─── Main API ─────────────────────────────────────────────────────────────────

async def get_brand_reputation(brand_name: str, amazon_reviews: list | None = None) -> dict:
    print(f"\n[Reputation] Analyzing brand: '{brand_name}'")

    google_reviews = []
    place = find_google_place(brand_name) if GOOGLE_PLACES_API_KEY else None

    if place:
        place_id = place.get("place_id")
        details = get_google_place_details(place_id) if place_id else {}
        google_reviews = normalize_google_reviews(details)
        print(f"[Reputation] Google reviews found: {len(google_reviews)}")
    else:
        print("[Reputation] No Google place match found or Google API key missing")

    amazon_normalized = normalize_amazon_reviews(amazon_reviews)
    print(f"[Reputation] Amazon fallback reviews available: {len(amazon_normalized)}")

    # Primary: Google if it has enough actual review text
    if len(google_reviews) >= 3:
        return build_reputation_insights(
            google_reviews,
            brand_name,
            source_name="google_places"
        )

    # Fallback: Amazon reviews
    if amazon_normalized:
        return build_reputation_insights(
            amazon_normalized,
            brand_name,
            source_name="amazon_reviews_fallback"
        )

    # Last resort: use whatever Google returned, even if small
    if google_reviews:
        return build_reputation_insights(
            google_reviews,
            brand_name,
            source_name="google_places_limited"
        )

    return {
        "brand": brand_name,
        "reputation_score_pct": None,
        "overall_label": "Brand review data unavailable.",
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
        "source": "no_brand_review_source_available",
    }