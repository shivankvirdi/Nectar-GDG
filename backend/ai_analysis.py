# ai_analysis.py
import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("❌ GROQ_API_KEY is missing from your .env file")

client = Groq(api_key=GROQ_API_KEY)


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

Return ONLY valid JSON (no markdown, no explanation) in this exact shape:
{{
  "pros": ["string", "string", "string"],
  "cons": ["string", "string", "string"],
  "verdict": "one sentence plain-English summary of whether this product is worth buying",
  "recommendation": "BUY" | "COMPARE" | "SKIP"
}}

Rules:
- pros/cons must come directly from patterns in the reviews, not invented
- verdict must be one sentence, max 20 words
- recommendation: BUY if score>=75, SKIP if score<50, otherwise COMPARE
- if reviews are overwhelmingly positive with no real cons, make the cons minor nitpicks only"""

    try:
        print("[AI Analysis] Calling Groq...")
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        print(f"[AI Analysis] ✅ Groq responded: {raw[:300]}")

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print("[AI Analysis] ❌ No JSON found in response")
            return _fallback(overall_score)

        result = json.loads(json_match.group())

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
            "verdict": result.get("verdict", "See scores above for details."),
            "recommendation": rec,
        }

    except Exception as e:
        print(f"[AI Analysis] ❌ EXCEPTION — {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return _fallback(overall_score)


def _fallback(overall_score: int) -> dict:
    rec = "BUY" if overall_score >= 75 else "SKIP" if overall_score < 50 else "COMPARE"
    return {
        "pros": ["Verified purchase ratio is strong", "Rating aligns with review sentiment", "Brand has positive reputation"],
        "cons": ["Limited review data available", "Could not extract detailed feedback", "Manual review recommended"],
        "verdict": "Analysis based on scores only — not enough review text available.",
        "recommendation": rec,
    }