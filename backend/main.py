from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

@app.post("/current-url")
async def receive_url(payload: UrlPayload):
    print("Received URL:", payload.url)
    return {"ok": True, "url": payload.url}
