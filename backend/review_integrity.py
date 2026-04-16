# review_integrity.py

import nltk                                          # Natural Language Toolkit — VADER lives inside here
nltk.download('vader_lexicon', quiet=True)           # downloads VADER's word scoring dictionary (one-time, silent)

from nltk.sentiment.vader import SentimentIntensityAnalyzer   # the actual sentiment scoring engine

# Create one shared analyzer — it's expensive to recreate, so we make it once at module level
sia = SentimentIntensityAnalyzer()


def score_single_review(review_text: str) -> dict:
    """
    Runs VADER on one review body string.
    Returns a dict with all 4 VADER scores:
      - 'pos': proportion of text that is positive (0.0 to 1.0)
      - 'neg': proportion of text that is negative (0.0 to 1.0)
      - 'neu': proportion of text that is neutral  (0.0 to 1.0)
      - 'compound': overall score from -1.0 (most negative) to +1.0 (most positive)
    The compound score is the single most useful number — it's what we use for all calculations.
    """
    return sia.polarity_scores(review_text)


def label_sentiment(compound_score: float) -> str:
    """
    Converts a raw VADER compound score into a human-readable label.
    Thresholds come from VADER's original research paper.
      >= 0.05  → Positive
      <= -0.05 → Negative
      in between → Neutral
    """
    if compound_score >= 0.05:
        return "Positive"
    elif compound_score <= -0.05:
        return "Negative"
    else:
        return "Neutral"


def check_star_sentiment_agreement(star_rating: int, compound_score: float) -> bool:
    """
    Compares the star rating a reviewer gave vs. what VADER detected in their text.
    If they disagree, it's a signal the review might be inauthentic (e.g. 5 stars but angry text).
    
    Agreement rules:
      - 4 or 5 stars → we expect compound >= 0.05 (positive text)
      - 1 or 2 stars → we expect compound <= -0.05 (negative text)
      - 3 stars      → neutral, so we accept anything
    Returns True if they agree, False if they conflict.
    """
    if star_rating >= 4:
        return compound_score >= 0.05       # high stars should have positive text
    elif star_rating <= 2:
        return compound_score <= -0.05      # low stars should have negative text
    else:
        return True                          # 3 stars is inherently mixed — always counts as agreement




def analyze_review_integrity(reviews: list) -> dict:
    """
    Master function for the Review Integrity module.
    Pulls 10-15 Amazon reviews via Canopy, runs VADER on each one,
    and returns a structured integrity report used by Nectar's UI.

    Output dict keys:
      - integrity_score_pct: the headline % shown in the Nectar UI (e.g. 84)
      - integrity_label: the subtitle text ("Most reviews appear organic and verified.")
      - verified_purchase_ratio: % of reviews marked as verified purchase
      - sentiment_consistency_ratio: % where star rating matches detected text sentiment
      - avg_compound_score: mean VADER compound across all reviews
      - sentiment_breakdown: {"Positive": N, "Neutral": N, "Negative": N}
      - review_details: list of per-review data (for debugging or expanded UI)
      - flags: dict of specific warning flags
    """

    if not reviews or len(reviews) == 0:                                  # guard: if Canopy returns nothing, bail gracefully
        return {"error": "No reviews found for this product."}

    review_details = []         # will hold per-review analysis
    compound_scores = []        # for computing the mean compound score
    verified_count = 0          # how many reviews are marked verified purchase
    agreement_count = 0         # how many star ratings agree with VADER's sentiment
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}

    for review in reviews:
        body = review.get("body", "")                # the full review text from Canopy
        star_rating = review.get("rating", 3)        # 1-5 star rating, default to 3 if missing
        is_verified = review.get("verifiedPurchase", False)  # boolean from Canopy

        if not body:                                 # skip reviews with no text (rating-only)
            continue

        vader_scores = score_single_review(body)     # run VADER — returns neg/neu/pos/compound dict
        compound = vader_scores["compound"]          # pull out the compound score
        label = label_sentiment(compound)            # "Positive", "Neutral", or "Negative"
        agrees = check_star_sentiment_agreement(star_rating, compound)  # does text match stars?

        # tally everything up
        compound_scores.append(compound)
        sentiment_counts[label] += 1
        if is_verified:
            verified_count += 1
        if agrees:
            agreement_count += 1

        # store the per-review breakdown for debugging or a future "expanded" UI state
        review_details.append({
            "title": review.get("title", ""),
            "rating": star_rating,
            "verified": is_verified,
            "compound_score": round(compound, 3),
            "sentiment_label": label,
            "star_text_agree": agrees,
        })

    total = len(review_details)                      # actual reviews we processed (text only)

    if total == 0:
        return {"error": "All reviews lacked text content."}

    # --- compute ratios ---
    verified_ratio = verified_count / total                    # e.g. 0.84
    consistency_ratio = agreement_count / total                # e.g. 0.91
    avg_compound = sum(compound_scores) / len(compound_scores) # e.g. 0.42

    # --- compute the headline integrity score ---
    # Weighted blend of verified ratio (60%) and star/text consistency (40%)
    # Both ratios are 0.0-1.0, we multiply by 100 to get a percentage
    raw_integrity = (verified_ratio * 0.60) + (consistency_ratio * 0.40)
    integrity_score_pct = round(raw_integrity * 100)           # e.g. 84

    # --- build the human-readable label ---
    if integrity_score_pct >= 80:
        integrity_label = "Most reviews appear organic and verified."
    elif integrity_score_pct >= 60:
        integrity_label = "Some reviews may be unverified — read carefully."
    else:
        integrity_label = "Low review integrity — treat ratings with caution."

    # --- flag any specific issues ---
    flags = {}
    if verified_ratio < 0.50:
        flags["low_verified_ratio"] = True              # less than half are verified purchases
    if consistency_ratio < 0.65:
        flags["star_text_mismatch"] = True              # many reviews have suspicious star/text combos
    if avg_compound < -0.1 and sum(r["rating"] for r in review_details) / total > 3.5:
        flags["inflated_ratings"] = True                # average star is high but text is negative — big red flag

    return {
        "integrity_score_pct": integrity_score_pct,
        "integrity_label": integrity_label,
        "verified_purchase_ratio": round(verified_ratio, 2),
        "sentiment_consistency_ratio": round(consistency_ratio, 2),
        "avg_compound_score": round(avg_compound, 3),
        "sentiment_breakdown": sentiment_counts,
        "review_details": review_details,
        "flags": flags,
    }