from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .vision_model import analyze_product_url
from .review_integrity import analyze_review_integrity
from .brand_reputation import get_brand_reputation
from .canopy_client import get_full_product_profile

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UrlPayload(BaseModel):
    url: str


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/analyze-product")
async def analyze_product(payload: UrlPayload):
    try:
        # 1. Core product analysis (vision model / canopy)
        product_analysis = analyze_product_url(payload.url)

        asin = product_analysis.get("asin")
        brand = product_analysis.get("brand")

        if not asin:
            raise HTTPException(
                status_code=400,
                detail="ASIN could not be extracted from URL"
            )

        # 2. Review integrity (Amazon reviews via Canopy)
        full_profile = get_full_product_profile(asin)
        reviews = full_profile.get("reviews", [])
        review_integrity = analyze_review_integrity(reviews)

        # 3. Brand reputation (Trustpilot scraping)
        brand_reputation = get_brand_reputation(brand) if brand else {
            "error": "Brand not found"
        }

        # 4. Unified response
        return {
            "ok": True,
            "product_analysis": product_analysis,
            "review_integrity": review_integrity,
            "brand_reputation": brand_reputation
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )