from .canopy_client import get_full_product_profile, search_similar_products
from .review_integrity import analyze_review_integrity

TEST_ASIN = "B0DQSJ4QHB"  ## shitty fake amazon airpods

result = get_full_product_profile(TEST_ASIN)
print("Title:", result["product"].get("title"))
print("Rating:", result["product"].get("rating"))
print("Reviews found:", len(result["reviews"]))
print("First review:", result["reviews"][0] if result["reviews"] else "none")

similar = search_similar_products("wireless headphones")
print(f"\nFound {len(similar)} similar products:")
for p in similar[:3]:
    price = (p.get("price") or {}).get("display")
    print(f"  - {p.get('title')} | {price} | rating {p.get('rating')}")

print("=" * 60)
print("REVIEW INTEGRITY — FULL TEST CASE")
print("=" * 60)

# ── Run the module ──
reviews = result.get("reviews", [])
integrity = analyze_review_integrity(reviews)

# ── Check for error key first ──
# If Canopy returned no reviews at all, the function returns {"error": "..."}
# We catch this before trying to access any other keys
if "error" in integrity:
    print(f"\n❌ Module returned an error: {integrity['error']}")
    print("   Possible causes:")
    print("   - ASIN has no reviews on Amazon")
    print("   - Canopy API key missing or invalid (.env not loaded)")
    print("   - Canopy free tier limit reached (100 req/month)")

else:
    # ── 1. Integrity Score Percentage ──
    # Expected: integer between 0 and 100
    score = integrity["integrity_score_pct"]
    print(f"\n[1] integrity_score_pct: {score}%")
    assert isinstance(score, int), "FAIL — score should be an integer"
    assert 0 <= score <= 100,      "FAIL — score should be between 0 and 100"
    print(f"    ✅ Valid integer in range 0–100")

    # ── 2. Integrity Label ──
    # Expected: one of three specific strings based on score thresholds
    label = integrity["integrity_label"]
    print(f"\n[2] integrity_label: '{label}'")
    valid_labels = [
        "Most reviews appear organic and verified.",
        "Some reviews may be unverified — read carefully.",
        "Low review integrity — treat ratings with caution.",
    ]
    assert label in valid_labels, f"FAIL — unexpected label: '{label}'"
    print(f"    ✅ Label matches expected threshold string")

    # ── 3. Verified Purchase Ratio ──
    # Expected: float between 0.0 and 1.0 (e.g. 0.84 = 84% verified)
    vpr = integrity["verified_purchase_ratio"]
    print(f"\n[3] verified_purchase_ratio: {vpr}")
    assert isinstance(vpr, float), "FAIL — should be a float"
    assert 0.0 <= vpr <= 1.0,      "FAIL — should be between 0.0 and 1.0"
    print(f"    ✅ Valid float — {round(vpr * 100)}% of reviews are verified purchases")

    # ── 4. Sentiment Consistency Ratio ──
    # Expected: float between 0.0 and 1.0
    # This measures how often star rating and VADER sentiment agree
    scr = integrity["sentiment_consistency_ratio"]
    print(f"\n[4] sentiment_consistency_ratio: {scr}")
    assert isinstance(scr, float), "FAIL — should be a float"
    assert 0.0 <= scr <= 1.0,      "FAIL — should be between 0.0 and 1.0"
    print(f"    ✅ Valid float — star/text agreement in {round(scr * 100)}% of reviews")

    # ── 5. Average Compound Score ──
    # Expected: float between -1.0 and +1.0 (VADER compound range)
    avg = integrity["avg_compound_score"]
    print(f"\n[5] avg_compound_score: {avg}")
    assert isinstance(avg, float), "FAIL — should be a float"
    assert -1.0 <= avg <= 1.0,     "FAIL — VADER compound must be between -1.0 and +1.0"
    if avg >= 0.05:
        sentiment_direction = "Overall Positive"
    elif avg <= -0.05:
        sentiment_direction = "Overall Negative"
    else:
        sentiment_direction = "Overall Neutral"
    print(f"    ✅ Valid VADER compound — {sentiment_direction}")

    # ── 6. Sentiment Breakdown ──
    # Expected: dict with exactly three keys: Positive, Neutral, Negative
    # All values should be non-negative integers that sum to total reviews analyzed
    breakdown = integrity["sentiment_breakdown"]
    print(f"\n[6] sentiment_breakdown: {breakdown}")
    assert isinstance(breakdown, dict),             "FAIL — should be a dict"
    assert "Positive" in breakdown,                 "FAIL — missing 'Positive' key"
    assert "Neutral"  in breakdown,                 "FAIL — missing 'Neutral' key"
    assert "Negative" in breakdown,                 "FAIL — missing 'Negative' key"
    assert all(v >= 0 for v in breakdown.values()), "FAIL — all counts should be >= 0"
    total_categorized = sum(breakdown.values())
    print(f"    ✅ All three keys present")
    print(f"    Positive: {breakdown['Positive']} | Neutral: {breakdown['Neutral']} | Negative: {breakdown['Negative']}")
    print(f"    Total categorized: {total_categorized} reviews")

    # ── 7. Review Details ──
    # Expected: list of dicts, one per review processed
    # Each dict must have all 6 expected keys
    details = integrity["review_details"]
    print(f"\n[7] review_details: {len(details)} reviews found")
    assert isinstance(details, list), "FAIL — should be a list"
    assert len(details) > 0,          "FAIL — should have at least one review"

    required_keys = {"title", "rating", "verified", "compound_score", "sentiment_label", "star_text_agree"}

    for i, review in enumerate(details):
        missing = required_keys - set(review.keys())
        assert not missing, f"FAIL — review #{i} missing keys: {missing}"

        # rating should be 1–5
        assert 1 <= review["rating"] <= 5, \
            f"FAIL — review #{i} has invalid rating: {review['rating']}"

        # compound_score should be in VADER range
        assert -1.0 <= review["compound_score"] <= 1.0, \
            f"FAIL — review #{i} compound out of range: {review['compound_score']}"

        # sentiment_label should be one of three values
        assert review["sentiment_label"] in ("Positive", "Neutral", "Negative"), \
            f"FAIL — review #{i} has invalid label: {review['sentiment_label']}"

        # star_text_agree should be a boolean
        assert isinstance(review["star_text_agree"], bool), \
            f"FAIL — review #{i} star_text_agree should be bool"

    print(f"    ✅ All {len(details)} review detail dicts are valid")

    # Print the first 3 reviews in full so you can read them
    print(f"\n    Sample (first 3 reviews):")
    for r in details[:3]:
        agree_symbol = "✅" if r["star_text_agree"] else "⚠️"
        print(f"      {agree_symbol} ⭐{r['rating']} | {r['sentiment_label']:8s} "
              f"| compound: {r['compound_score']:+.3f} "
              f"| verified: {r['verified']} "
              f"| '{r['title'][:40]}'")

    # ── 8. Flags ──
    # Expected: dict — may be empty (no flags) or contain specific warning keys
    flags = integrity["flags"]
    print(f"\n[8] flags: {flags}")
    assert isinstance(flags, dict), "FAIL — flags should be a dict"

    known_flag_keys = {"low_verified_ratio", "star_text_mismatch", "inflated_ratings"}
    unexpected = set(flags.keys()) - known_flag_keys
    assert not unexpected, f"FAIL — unexpected flag keys found: {unexpected}"

    if not flags:
        print(f"    ✅ No integrity flags raised — reviews appear clean")
    else:
        print(f"    ⚠️  Flags raised:")
        for flag, value in flags.items():
            print(f"       - {flag}: {value}")

    # ── Final Summary ──
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"  ASIN:              {TEST_ASIN}")
    print(f"  Score:             {score}%")
    print(f"  Label:             {label}")
    print(f"  Verified ratio:    {round(vpr * 100)}%")
    print(f"  Consistency ratio: {round(scr * 100)}%")
    print(f"  Avg compound:      {avg:+.3f} ({sentiment_direction})")
    print(f"  Breakdown:         {breakdown}")
    print(f"  Reviews analyzed:  {len(details)}")
    print(f"  Flags:             {flags if flags else 'None'}")
    print("=" * 60)