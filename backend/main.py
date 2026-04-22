import sys
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .vision_model import analyze_product_url
from .ai_analysis import explain_score_with_ai

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

class ExplainScorePayload(BaseModel):
    metric: str
    analysis: dict[str, Any]

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/current-url")
async def analyze_product(payload: UrlPayload):
    try:
        analysis = await analyze_product_url(payload.url)
        return {"ok": True, "analysis": analysis}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/explain-score")
async def explain_score(payload: ExplainScorePayload):
    try:
        answer = explain_score_with_ai(payload.metric, payload.analysis)
        return {"ok": True, **answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"[REQUEST] {request.method} {request.url}")
    response = await call_next(request)
    print(f"[RESPONSE] Status: {response.status_code}")
    return response