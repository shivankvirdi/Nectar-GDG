# ai_analysis.py
import os
import json
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY is missing from your .env file")

client = genai.Client(api_key=GEMINI_API_KEY)


def get_ai_verdict(
    title: str,
    reviews: list,
    overall_score: int,
    integrity_score: int,
    reputation_score: int,
) -> dict:

    review_snippets = "\n".join(
        f"- [{r.get('rating', '?')}★] {r.get('body', '')[:200]}"
        for r in reviews[:15]
        if r.get("body", "").strip()
    )

    print(f"[AI Analysis] reviews received: {len(reviews)}")
    print(f"[AI Analysis] snippets built: {len(review_snippets.splitlines())}")

    if not review_snippets.strip():
        print("[AI Analysis] No usable review text — using fallback")
        return _fallback(overall_score)

    prompt = f"""You are a shopping assistant analyzing Amazon product reviews.

Product: {title}
Trust Score: {overall_score}/100
Review Integrity: {integrity_score}/100
Brand Reputation: {reputation_score}/100

Customer reviews:
{review_snippets}

Return JSON only.

Rules:
- pros/cons must come directly from patterns in the reviews, not invented
- verdict must be one sentence, max 20 words
- recommendation: BUY if score>=75, SKIP if score<50, otherwise COMPARE
- if reviews are overwhelmingly positive with no real cons, make the cons minor nitpicks only
"""

    schema = {
        "type": "object",
        "properties": {
            "pros": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "cons": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "verdict": {"type": "string"},
            "recommendation": {
                "type": "string",
                "enum": ["BUY", "COMPARE", "SKIP"],
            },
        },
        "required": ["pros", "cons", "verdict", "recommendation"],
    }

    try:
        print("[AI Analysis] Calling Gemini...")

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]

        for model_name in models_to_try:
            for attempt in range(3):
                try:
                    print(f"[AI Analysis] Trying {model_name} (attempt {attempt + 1})")

                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.3,
                            response_mime_type="application/json",
                            response_json_schema=schema,
                        ),
                    )

                    raw = (response.text or "").strip()
                    print(f"[AI Analysis] ✅ Gemini responded: {raw[:300]}")

                    result = json.loads(raw)

                    pros = result.get("pros", [])
                    cons = result.get("cons", [])

                    while len(pros) < 3:
                        pros.append("No further pros identified")
                    while len(cons) < 3:
                        cons.append("No further cons identified")

                    rec = result.get("recommendation", "COMPARE")
                    if rec not in ("BUY", "COMPARE", "SKIP"):
                        rec = "COMPARE"

                    return {
                        "pros": pros[:3],
                        "cons": cons[:3],
                        "verdict": result.get("verdict", "See scores above."),
                        "recommendation": rec,
                    }

                except Exception as e:
                    print(f"[AI Analysis] ⚠️ {model_name} failed: {e}")
                    time.sleep(1.5 * (attempt + 1))

        print("[AI Analysis] ❌ All Gemini attempts failed")
        return _fallback(overall_score)

    except Exception as e:
        print(f"[AI Analysis] ❌ FINAL EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return _fallback(overall_score)


def _fallback(overall_score: int) -> dict:
    rec = "BUY" if overall_score >= 75 else "SKIP" if overall_score < 50 else "COMPARE"
    return {
        "pros": [
            "Verified purchase ratio is strong",
            "Rating aligns with review sentiment",
            "Brand has positive reputation",
        ],
        "cons": [
            "Limited review data available",
            "Could not extract detailed feedback",
            "Manual review recommended",
        ],
        "verdict": "Analysis based on scores only — not enough review text available.",
        "recommendation": rec,
    }