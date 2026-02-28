"""
urls.py  FastAPI entrypoint for agentsuite-2.0

Endpoints:
- GET  /health
- POST /v1/support/chat
"""
from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from license import handle_support_chat
from settings import SETTINGS

app = FastAPI(title="agentsuite-2.0", version="0.1.0")


def _check_secret(shared_secret: str | None) -> None:
    if not SETTINGS.REQUIRE_SHARED_SECRET:
        return
    expected = SETTINGS.PPA_WP_SHARED_SECRET
    if not expected:
        raise HTTPException(status_code=500, detail="Server misconfigured: missing PPA_WP_SHARED_SECRET")
    if not shared_secret or shared_secret != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/support/chat")
async def support_chat(
    request: Request,
    x_ppa_shared_secret: str | None = Header(default=None, convert_underscores=False),
    x_shared_secret: str | None = Header(default=None, convert_underscores=False),
    x_api_key: str | None = Header(default=None, convert_underscores=False),
):
    shared_secret = x_ppa_shared_secret or x_shared_secret or x_api_key
    _check_secret(shared_secret)

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "bad_request",
                "detail": str(e),
                "assistant_message": "I couldnt read that request. Please try again.",
                "suggested_actions": [],
                "escalation_offered": True,
            },
        )

    resp = handle_support_chat(payload)
    return JSONResponse(status_code=200, content=resp)
