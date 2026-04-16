from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .vision_model import analyze_product_url

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
async def receive_url(payload: UrlPayload):
    try:
        analysis = analyze_product_url(payload.url)
        return {
            "ok": True,
            "url": payload.url,
            "analysis": analysis,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error