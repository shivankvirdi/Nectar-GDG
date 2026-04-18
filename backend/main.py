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


@app.post("/current-url")
async def analyze_product(payload: UrlPayload):
    try:
        analysis = analyze_product_url(payload.url)
        return { "ok": True, "analysis": analysis }  # key matches frontend
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")