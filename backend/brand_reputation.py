# brand_reputation.py

import re
import math
import requests
import json
import time
from collections import Counter
from bs4 import BeautifulSoup
import nltk
nltk.download('vader_lexicon',              quiet=True)
nltk.download('stopwords',                  quiet=True)
nltk.download('punkt',                      quiet=True)
nltk.download('punkt_tab',                  quiet=True)
nltk.download('wordnet',                    quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)

from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize
from nltk.stem import WordNetLemmatizer

sia        = SentimentIntensityAnalyzer()
lemmatizer = WordNetLemmatizer()
STOP_WORDS = set(stopwords.words('english'))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── Trustpilot helpers ───────────────────────────────────────────────────────

def normalize_brand(brand: str) -> str:
    if not brand: return ""
    brand = brand.lower().strip()
    brand = re.sub(r"[^a-z0-9 ]", "", brand)
    return re.sub(r"\s+", " ", brand)

def guess_domain(brand: str) -> str:
    if not brand: return ""
    clean = re.sub(r"[^a-z0-9]", "", brand.lower())
    return f"{clean}.com"

def get_trustpilot_candidates(brand: str):
    return [brand, normalize_brand(brand), brand.replace(" ", ""), guess_domain(brand)]

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
        page_data  = json.loads(next_data_tag.string)
        page_props = page_data.get("props", {}).get("pageProps", {})
        business_units = (
            page_props.get("businessUnits")
            or page_props.get("businesses")
            or page_props.get("searchResults", {}).get("businessUnits")
            or page_props.get("searchResult", {}).get("businessUnits")
            or page_props.get("hits")
            or []
        )
        if not business_units and isinstance(page_props.get("pageData"), dict):
            business_units = page_props["pageData"].get("businessUnits", [])
        if not business_units:
            print(f"[Trustpilot] No businesses found for '{brand_name}'")
            return None
        first = next((b for b in business_units if brand_name.lower() in (b.get("name") or "").lower()), None)
        if not first:
            first = business_units[0]
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
    reviews = []
    for page_num in range(1, 3):
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
            page_reviews = (
                page_data.get("props", {}).get("pageProps", {}).get("reviews")
                or page_data.get("props", {}).get("reviews")
                or []
            )
            for review in page_reviews:
                text = review.get("text", "")
                if text:
                    reviews.append({
                        "text":   text,
                        "title":  review.get("title", ""),
                        "rating": review.get("rating", 3),
                    })
            time.sleep(1.5)
        except Exception as e:
            print(f"[Trustpilot] Error on page {page_num}: {e}")
            break
        if len(reviews) >= max_reviews:
            break
    return reviews[:max_reviews]


# ─── Keyword config ───────────────────────────────────────────────────────────

BRAND_NOISE_WORDS = {
    # generic filler
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
    # product/food noise (leak from wrong pages)
    "protein", "sugar", "taste", "chocolate", "drink", "banana", "cream",
    "bike", "ride", "rider", "motor", "cycle", "wheel", "gear", "engine",
    "team", "market", "store", "shop", "brand", "company", "business",
    # common names that leak through as keywords
    "john", "jane", "mike", "dave", "mark", "paul", "james", "david",
    "chris", "steve", "lind", "harley", "davidson", "ford", "honda",
    # review meta-words
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

NEGATION_WORDS = {
    "not", "no", "never", "cant", "cannot", "wont", "dont",
    "doesnt", "didnt", "isnt", "wasnt", "barely", "hardly",
    "scarcely", "nothing", "neither",
}

MIN_WORD_LENGTH = 5   # skip short words like "guy", "bike", "lind"
MIN_DOC_FREQ    = 3   # must appear in at least 3 reviews (raised from 2)


# ─── Proper noun detection ────────────────────────────────────────────────────

def _build_proper_noun_set(reviews: list, field: str = "text") -> set[str]:
    """
    Collects words that appear capitalised mid-sentence in the majority of
    their occurrences — strong signal they are names/brands, not concepts.
    We exclude sentence-start positions to avoid false positives.
    """
    cap_count:   Counter = Counter()
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
                # capitalised but NOT at sentence start → likely a proper noun
                if i > 0 and tok[0].isupper():
                    cap_count[clean] += 1

    # if a word is capitalised >60% of the time mid-sentence, treat as proper noun
    proper_nouns = set()
    for word, total in total_count.items():
        if total >= 2 and cap_count[word] / total > 0.6:
            proper_nouns.add(word)

    return proper_nouns


# ─── Extraction helpers ───────────────────────────────────────────────────────

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
    pairs  = []
    for i, tok in enumerate(tokens[:-1]):
        if tok.replace("'", "") in NEGATION_WORDS:
            nxt = tokens[i + 1]
            if (len(nxt) >= MIN_WORD_LENGTH
                    and nxt not in STOP_WORDS
                    and nxt not in BRAND_NOISE_WORDS):
                pairs.append(f"not {_lemma(nxt)}")
    return pairs


# ─── Main keyword extraction ──────────────────────────────────────────────────

def extract_common_keywords(reviews: list, top_n: int = 10) -> list:
    total = len(reviews)
    if total == 0:
        return []

    # Build proper noun blocklist from the actual review text
    proper_nouns = _build_proper_noun_set(reviews, field="text")
    print(f"[Keywords] Proper nouns detected and blocked: {proper_nouns}")

    word_counts:     Counter = Counter()
    word_doc_freq:   Counter = Counter()
    bigram_counts:   Counter = Counter()
    bigram_doc_freq: Counter = Counter()
    negation_counts: Counter = Counter()

    for review in reviews:
        text = review.get("text", "") or ""
        if not text:
            continue
        text_lower = text.lower()

        # ── lemmatized unigrams ────────────────────────────────────────────
        raw_words   = re.findall(r"[a-z]{%d,}" % MIN_WORD_LENGTH, text_lower)
        seen_lemmas: set[str] = set()
        for w in raw_words:
            lemma = _lemma(w)
            if (lemma not in STOP_WORDS
                    and lemma not in BRAND_NOISE_WORDS
                    and lemma not in proper_nouns
                    and len(lemma) >= MIN_WORD_LENGTH):
                word_counts[lemma] += 1
                if lemma not in seen_lemmas:
                    word_doc_freq[lemma] += 1
                    seen_lemmas.add(lemma)

        # ── curated bigrams ────────────────────────────────────────────────
        seen_bg: set[str] = set()
        for bg in BRAND_BIGRAMS:
            if bg in text_lower:
                bigram_counts[bg] += 1
                if bg not in seen_bg:
                    bigram_doc_freq[bg] += 1
                    seen_bg.add(bg)

        # ── negation bigrams ───────────────────────────────────────────────
        for neg in _negation_bigrams(text):
            negation_counts[neg] += 1

    # ── TF-IDF-style scoring ──────────────────────────────────────────────
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

    # ── sentence-level sentiment ──────────────────────────────────────────
    keywords = []
    for term in top_terms:
        is_negation = term.startswith("not ") and " " in term
        is_bigram   = " " in term

        if is_bigram:
            raw_count = negation_counts[term] if is_negation else bigram_counts[term]
        else:
            raw_count = word_counts[term]

        if is_negation:
            sentiment = "negative"
        else:
            sscores = _sentence_scores_for_term(term, reviews, field="text")
            avg     = sum(sscores) / len(sscores) if sscores else 0.0
            sentiment = "positive" if avg >= 0.05 else "negative" if avg <= -0.05 else "neutral"

        keywords.append({"word": term, "count": raw_count, "sentiment": sentiment})

    return keywords


# ─── Reputation analysis ──────────────────────────────────────────────────────

def build_reputation_insights(reviews: list, brand_name: str) -> dict:
    if not reviews:
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
    support_texts  = []
    shipping_texts = []
    quality_texts  = []

    for review in reviews:
        text       = review["text"]
        text_lower = text.lower()
        compound   = sia.polarity_scores(text)["compound"]
        compound_scores.append(compound)

        if compound >= 0.05:    pos_count += 1
        elif compound <= -0.05: neg_count += 1
        else:                   neu_count += 1

        if any(kw in text_lower for kw in ["support", "service", "help", "response", "refund", "return", "agent"]):
            support_texts.append(compound)
        if any(kw in text_lower for kw in ["shipping", "delivery", "arrived", "package", "delayed", "late", "fast", "slow"]):
            shipping_texts.append(compound)
        if any(kw in text_lower for kw in ["quality", "durable", "broke", "build", "material", "lasted", "cheap", "premium"]):
            quality_texts.append(compound)

    total        = len(compound_scores)
    avg_compound = sum(compound_scores) / total if total > 0 else 0

    def scores_to_status(scores: list) -> str:
        if not scores: return "Neutral"
        mean = sum(scores) / len(scores)
        if mean >= 0.05:   return "Positive"
        if mean <= -0.05:  return "Caution"
        return "Neutral"

    insights = [
        {"topic": "Customer Support",    "status": scores_to_status(support_texts)},
        {"topic": "Shipping & Delivery", "status": scores_to_status(shipping_texts)},
        {"topic": "Build Quality",       "status": scores_to_status(quality_texts)},
    ]

    avg_rating           = sum(r.get("rating", 3) for r in reviews) / total if total > 0 else 3
    sentiment_score      = ((avg_compound + 1) / 2) * 100
    rating_score         = (avg_rating / 5) * 100
    reputation_score_pct = round((sentiment_score * 0.45) + (rating_score * 0.55)) if total > 0 else None

    if   reputation_score_pct >= 80: overall_label = "Strong overall brand reputation on Trustpilot."
    elif reputation_score_pct >= 65: overall_label = "Mostly positive brand reputation with some concerns."
    elif reputation_score_pct >= 50: overall_label = "Mixed brand reputation on Trustpilot."
    else:                            overall_label = "Weak brand reputation based on recent Trustpilot reviews."

    return {
        "brand":                brand_name,
        "reputation_score_pct": reputation_score_pct,
        "overall_label":        overall_label,
        "avg_compound":         round(avg_compound, 3),
        "positive_pct":         round((pos_count / total) * 100) if total > 0 else 0,
        "negative_pct":         round((neg_count / total) * 100) if total > 0 else 0,
        "reviews_analyzed":     total,
        "insights":             insights,
        "commonKeywords":       extract_common_keywords(reviews),
    }


def get_brand_reputation(brand_name: str) -> dict:
    print(f"\n[Reputation] Analyzing brand: '{brand_name}'")
    slug = find_trustpilot_slug(brand_name)
    if not slug:
        print(f"[Reputation] No Trustpilot slug found — returning neutral fallback")
        return {
            "brand":                brand_name,
            "reputation_score_pct": None,
            "overall_label":        "Trustpilot data unavailable — fallback required",
            "avg_compound":         None,
            "positive_pct":         None,
            "negative_pct":         None,
            "reviews_analyzed":     0,
            "insights": [
                {"topic": "Customer Support",    "status": "Unknown"},
                {"topic": "Shipping & Delivery", "status": "Unknown"},
                {"topic": "Build Quality",       "status": "Unknown"},
            ],
            "commonKeywords": [],
            "source": "no_trustpilot_data",
        }
    reviews = scrape_trustpilot_reviews(slug)
    return build_reputation_insights(reviews, brand_name)