# nlp_utils.py
"""
Shared NLP utilities used by review_integrity.py and brand_reputation.py.
Usage:
    from .nlp_utils import extract_keywords, sia, STOP_WORDS
"""

import re
import math
from collections import Counter

from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize
from nltk.stem import WordNetLemmatizer

FALLBACK_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "had", "has", "have", "he", "her", "his", "i", "in", "is", "it", "its",
    "me", "my", "not", "of", "on", "or", "our", "she", "so", "that", "the",
    "their", "them", "they", "this", "to", "was", "we", "were", "with", "you",
    "your",
}


class _FallbackSentimentIntensityAnalyzer:
    _positive = {
        "amazing", "best", "comfortable", "durable", "easy", "excellent",
        "fast", "good", "great", "happy", "love", "loved", "perfect",
        "quality", "recommend", "reliable", "strong", "works",
    }
    _negative = {
        "bad", "broken", "cheap", "defective", "disappointed", "failed",
        "hard", "hate", "late", "poor", "refund", "slow", "terrible",
        "uncomfortable", "weak", "worse", "worst",
    }

    def polarity_scores(self, text: str) -> dict[str, float]:
        words = re.findall(r"[a-z']+", str(text or "").lower())
        if not words:
            return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}
        positives = sum(1 for word in words if word in self._positive)
        negatives = sum(1 for word in words if word in self._negative)
        total = max(1, positives + negatives)
        compound = max(-1.0, min(1.0, (positives - negatives) / total))
        return {
            "neg": negatives / len(words),
            "neu": max(0.0, 1.0 - ((positives + negatives) / len(words))),
            "pos": positives / len(words),
            "compound": compound,
        }


class _FallbackLemmatizer:
    def lemmatize(self, word: str) -> str:
        word = word.lower()
        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"
        if len(word) > 3 and word.endswith("s"):
            return word[:-1]
        return word


def _build_sentiment_analyzer():
    try:
        return SentimentIntensityAnalyzer()
    except LookupError:
        return _FallbackSentimentIntensityAnalyzer()


def _build_stop_words() -> set[str]:
    try:
        return set(stopwords.words("english"))
    except LookupError:
        return set(FALLBACK_STOP_WORDS)


def _build_lemmatizer():
    try:
        candidate = WordNetLemmatizer()
        candidate.lemmatize("tests")
        return candidate
    except LookupError:
        return _FallbackLemmatizer()


sia        = _build_sentiment_analyzer()
lemmatizer = _build_lemmatizer()
STOP_WORDS = _build_stop_words()

# Words that negate the following token — shared across both modules.
NEGATION_WORDS = {
    "not", "no", "never", "cant", "cannot", "wont", "dont",
    "doesnt", "didnt", "isnt", "wasnt", "barely", "hardly",
    "scarcely", "nothing", "neither",
}


# ─── Core helpers ─────────────────────────────────────────────────────────────

def lemmatize(word: str) -> str:
    """Return the noun-lemma root of a word (batteries → battery)."""
    return lemmatizer.lemmatize(word.lower())


def sentence_scores_for_term(term: str, reviews: list, field: str) -> list[float]:
    """
    Score only the sentences that contain *term*, not the whole review body.

    Why: "Love the build quality. Battery is terrible." scores ~neutral overall.
    Scoring the battery sentence in isolation correctly returns negative, so
    'battery' gets the right sentiment label.
    """
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


def build_proper_noun_set(
    reviews: list,
    field: str,
    min_length: int = 5,
) -> set[str]:
    """
    Detect words that appear capitalised mid-sentence the majority of the time.
    These are likely proper nouns (brand names, product names) and should be
    excluded from keyword extraction to avoid noise.
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
                if len(clean) < min_length:
                    continue
                total_count[clean] += 1
                # capitalised mid-sentence (not sentence-start) → likely proper noun
                if i > 0 and tok and tok[0].isupper():
                    cap_count[clean] += 1

    proper_nouns: set[str] = set()
    for word, total in total_count.items():
        if total >= 2 and cap_count[word] / total > 0.6:
            proper_nouns.add(word)
    return proper_nouns


def _negation_bigrams_for_text(
    text: str,
    noise_words: set,
    min_length: int,
) -> list[str]:
    """Find 'not working', 'never fits' patterns and return as forced-negative terms."""
    tokens = re.findall(r"[a-z']+", text.lower())
    pairs  = []
    for i, tok in enumerate(tokens[:-1]):
        if tok.replace("'", "") in NEGATION_WORDS:
            nxt = tokens[i + 1]
            if len(nxt) >= min_length and nxt not in STOP_WORDS and nxt not in noise_words:
                pairs.append(f"not {lemmatize(nxt)}")
    return pairs


# ─── Main generalised keyword extractor ──────────────────────────────────────

def extract_keywords(
    reviews: list,
    *,
    field: str,
    noise_words: set,
    boost_words: set,
    curated_bigrams: set,
    min_doc_freq: int       = 2,
    min_word_length: int    = 4,
    use_proper_noun_filter: bool = False,
    top_n: int              = 10,
) -> list[dict]:
    """
    Extract the top-N most meaningful keywords from a list of review dicts.

    Parameters
    ----------
    reviews             : list of dicts, each must contain the `field` key
    field               : which review key holds the text ('body' or 'text')
    noise_words         : domain-specific filler words to exclude
    boost_words         : domain-specific signal words (get 2× weight)
    curated_bigrams     : set of meaningful two-word phrases to track
    min_doc_freq        : minimum number of reviews a term must appear in
    min_word_length     : minimum character length for unigrams
    use_proper_noun_filter : if True, detect and exclude proper nouns
    top_n               : how many keywords to return

    Returns
    -------
    list of dicts: [{"word": str, "count": int, "sentiment": "positive"|"negative"|"neutral"}]
    """
    total = len(reviews)
    if total == 0:
        return []

    proper_nouns: set[str] = set()
    if use_proper_noun_filter:
        proper_nouns = build_proper_noun_set(reviews, field, min_word_length)
        if proper_nouns:
            print(f"[nlp_utils] Proper nouns blocked: {proper_nouns}")

    word_counts:     Counter = Counter()
    word_doc_freq:   Counter = Counter()
    bigram_counts:   Counter = Counter()
    bigram_doc_freq: Counter = Counter()
    negation_counts: Counter = Counter()

    for review in reviews:
        text = review.get(field, "") or ""
        if not text:
            continue
        text_lower = text.lower()

        # ── lemmatized unigrams ────────────────────────────────────────────
        raw_words   = re.findall(r"[a-z]{%d,}" % min_word_length, text_lower)
        seen_lemmas: set[str] = set()
        for w in raw_words:
            lem = lemmatize(w)
            if (
                lem not in STOP_WORDS
                and lem not in noise_words
                and lem not in proper_nouns
                and len(lem) >= min_word_length
            ):
                word_counts[lem] += 1
                if lem not in seen_lemmas:
                    word_doc_freq[lem] += 1
                    seen_lemmas.add(lem)

        # ── curated bigrams ────────────────────────────────────────────────
        seen_bg: set[str] = set()
        for bg in curated_bigrams:
            if bg in text_lower:
                bigram_counts[bg] += 1
                if bg not in seen_bg:
                    bigram_doc_freq[bg] += 1
                    seen_bg.add(bg)

        # ── negation bigrams ───────────────────────────────────────────────
        for neg in _negation_bigrams_for_text(text, noise_words, min_word_length):
            negation_counts[neg] += 1

    # ── TF-IDF-style scoring ──────────────────────────────────────────────
    def idf(df: int) -> float:
        return math.log(total / (1 + df)) + 1.0

    scored: dict[str, float] = {}

    for lem, count in word_counts.items():
        df = word_doc_freq[lem]
        if df < min_doc_freq:
            continue
        boost = 2.0 if lem in boost_words else 1.0
        scored[lem] = count * idf(df) * boost

    for bg, count in bigram_counts.items():
        df = bigram_doc_freq[bg]
        if df < min_doc_freq:
            continue
        scored[bg] = count * idf(df) * 3.0     # bigrams: 3× (more specific)

    for neg, count in negation_counts.items():
        if count >= min_doc_freq:
            scored[neg] = count * 4.0           # negations: 4× (high signal)

    top_terms = sorted(scored, key=scored.__getitem__, reverse=True)[:top_n]

    # ── sentence-level sentiment per top term ─────────────────────────────
    keywords: list[dict] = []
    for term in top_terms:
        is_negation = term.startswith("not ") and " " in term
        is_bigram   = " " in term

        raw_count = (
            negation_counts[term] if is_bigram and is_negation
            else bigram_counts[term] if is_bigram
            else word_counts[term]
        )

        if is_negation:
            sentiment = "negative"
        else:
            sscores = sentence_scores_for_term(term, reviews, field)
            avg     = sum(sscores) / len(sscores) if sscores else 0.0
            sentiment = (
                "positive" if avg >= 0.05
                else "negative" if avg <= -0.05
                else "neutral"
            )

        keywords.append({"word": term, "count": raw_count, "sentiment": sentiment})

    return keywords
