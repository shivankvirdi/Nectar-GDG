import sys
import os
import asyncio

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .vision_model import ScanCancelled, analyze_product_url
from .ai_analysis import explain_score_with_ai

NECTAR_SECRET = os.getenv("NECTAR_API_SECRET", "")

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
    scanId: str | None = None

class CancelScanPayload(BaseModel):
    scanId: str

class ExplainScorePayload(BaseModel):
    metric: str
    analysis: dict[str, Any]

active_scan_cancellations: dict[str, asyncio.Event] = {}

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/current-url")
async def analyze_product(payload: UrlPayload):
    cancel_event: asyncio.Event | None = None
    if payload.scanId:
        cancel_event = asyncio.Event()
        active_scan_cancellations[payload.scanId] = cancel_event

    try:
        analysis = await analyze_product_url(
            payload.url,
            is_cancelled=cancel_event.is_set if cancel_event else None,
        )
        return {"ok": True, "analysis": analysis}
    except ScanCancelled:
        return {"ok": False, "cancelled": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if payload.scanId:
            active_scan_cancellations.pop(payload.scanId, None)

@app.post("/cancel-scan")
async def cancel_scan(payload: CancelScanPayload):
    cancel_event = active_scan_cancellations.get(payload.scanId)
    if cancel_event:
        cancel_event.set()
    return {"ok": True, "cancelled": bool(cancel_event)}

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

async def verify_secret(request: Request, call_next):
    # Allow health checks through unauthenticated
    if request.url.path == "/health":
        return await call_next(request)
    token = request.headers.get("X-Nectar-Secret", "")
    if not NECTAR_SECRET or token != NECTAR_SECRET:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    
    return await call_next(request)
