"""
store_post.py
-------------
Receives final/draft posts from WordPress and stores analytics for billing/telemetry.

Enhancements in this version:
- Accepts sealed envelope (Base64 + HMAC) sent by WP proxy to avoid CF/WAF HTML inspection
- Verifies HMAC using PPA_SHARED_KEY and optional timestamp window
- CORS with allowlist (reflect Origin when allowed)
- OPTIONS preflight allowed WITHOUT X-PPA-Key (Cloudflare-friendly)
- POST requires X-PPA-Key (outer layer) OR sealed envelope verification
- Bulletproof persistence (no exception ever bubbles to client)
"""

from __future__ import annotations

import base64
import hmac
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from django.apps import apps
from django.conf import settings
from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# ----- CORS helpers ---------------------------------------------------------

def _allowed_origins():
    """List of allowed origins for admin UI requests (WP dashboard)."""
    return getattr(
        settings,
        "PPA_ALLOWED_ORIGINS",
        [
            "https://techwithwayne.com",
            "https://www.techwithwayne.com",
        ],
    )

def _origin_allowed(origin: str | None) -> bool:
    return bool(origin) and origin in _allowed_origins()

def _apply_cors(resp: HttpResponse, request) -> HttpResponse:
    origin = request.headers.get("Origin") or request.META.get("HTTP_ORIGIN")
    if _origin_allowed(origin):
        resp["Access-Control-Allow-Origin"] = origin
    resp["Vary"] = "Origin"
    resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key"
    resp["Access-Control-Max-Age"] = "600"
    return resp

def _options_response(request):
    return _apply_cors(HttpResponse(status=204), request)

def _json(data: Dict[str, Any], status: int, request: Optional[HttpRequest] = None):
    res = JsonResponse(data, status=status)
    if request is not None:
        res = _apply_cors(res, request)
    return res

def _unauthorized(request, reason: str):
    payload = {"ok": False, "error": "Unauthorized"}
    if getattr(settings, "DEBUG", False):
        payload["diagnostic"] = {"reason": reason}
    return _json(payload, 403, request)

# ----- Safe utilities -------------------------------------------------------

def _safe_json_dump(obj: Any) -> str:
    """Robust JSON stringify for logging or storage fallbacks."""
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return str(obj)

def _field_internal_type(field) -> str:
    try:
        return field.get_internal_type()
    except Exception:
        return ""

def _coerce_for_field(name: str, value: Any, field) -> Any:
    """
    Coerce incoming payload value to match DB field expectations:
    - If dict/list and field is not JSONField, store JSON string
    - If CharField with max_length, truncate
    - Otherwise return as-is
    """
    ftype = _field_internal_type(field)
    if isinstance(value, (dict, list)) and "JSONField" not in ftype:
        return _safe_json_dump(value)
    if ftype == "CharField":
        max_len = getattr(field, "max_length", None)
        if isinstance(value, str) and isinstance(max_len, int) and max_len > 0 and len(value) > max_len:
            return value[: max_len]
    return value

# ----- Envelope verification ------------------------------------------------

def _verify_and_unseal_envelope(obj: Dict[str, Any], shared_key: str, max_skew_sec: int = 900) -> Optional[Dict[str, Any]]:
    """
    If the incoming object contains a Base64+HMAC envelope, verify and return inner payload dict.
    Envelope shape:
        { "ver": 1, "b64": "<base64 of original JSON>", "ts": <unix>, "sig": "<hex hmac>" }
    HMAC is computed on:   b64 + "|" + ts
    """
    if not isinstance(obj, dict):
        return None
    if not all(k in obj for k in ("b64", "ts", "sig")):
        return None

    try:
        b64 = obj["b64"]
        ts  = int(obj["ts"])
        sig = obj["sig"]
    except Exception:
        return None

    # Time skew check (basic replay protection)
    try:
        now = int(time.time())
        if abs(now - ts) > max_skew_sec:
            logger.warning("[store_post] Envelope timestamp out of window (now=%s ts=%s)", now, ts)
            # We still proceed to verify HMAC, but you could choose to reject here.
    except Exception:
        pass

    # HMAC check
    mac = hmac.new(shared_key.encode("utf-8"), (f"{b64}|{ts}").encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, str(sig)):
        logger.warning("[store_post] Envelope HMAC mismatch")
        return None

    # Decode inner JSON
    try:
        inner = base64.b64decode(b64.encode("utf-8"))
        payload = json.loads(inner.decode("utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception as e:
        logger.exception("[store_post] Envelope decode failed: %s", e)
    return None

# ----- DB persistence --------------------------------------------------------

def _persist_article(payload: Dict[str, Any], request_ms: float) -> Dict[str, Any]:
    """
    Attempt to persist the payload into postpress_ai.StoredArticle if present.
    - Maps only known model fields.
    - Coerces problematic values to safe representations.
    - Falls back to a minimal subset if the full create fails.
    """
    try:
        Model = apps.get_model("postpress_ai", "StoredArticle")
    except LookupError:
        logger.info("[store_post] Model postpress_ai.StoredArticle not found; skipping DB save.")
        return {"stored": False, "id": None, "mode": "no_model"}

    try:
        # Build safe kwargs for create
        model_fields = {f.name: f for f in Model._meta.get_fields() if hasattr(f, "attname")}
        create_kwargs = {}
        for key, val in payload.items():
            if key in model_fields:
                create_kwargs[key] = _coerce_for_field(key, val, model_fields[key])

        # Optionally persist request time
        if "request_ms" in model_fields:
            create_kwargs["request_ms"] = request_ms

        obj = Model.objects.create(**create_kwargs)
        logger.info("[store_post] Stored article pk=%s (mode=full)", getattr(obj, "pk", None))
        return {"stored": True, "id": getattr(obj, "pk", None), "mode": "full"}

    except Exception as e:
        logger.exception("[store_post] Primary save failed; attempting fallback minimal save. Error=%s", e)

        minimal_keys = ["title", "status", "source", "wp_post_id"]
        try:
            model_fields = {f.name: f for f in Model._meta.get_fields() if hasattr(f, "attname")}
            minimal_kwargs = {}
            for k in minimal_keys:
                if k in model_fields and k in payload:
                    minimal_kwargs[k] = _coerce_for_field(k, payload.get(k), model_fields[k])
            if "request_ms" in model_fields:
                minimal_kwargs["request_ms"] = request_ms

            obj = Model.objects.create(**minimal_kwargs)
            logger.info("[store_post] Stored article pk=%s (mode=minimal)", getattr(obj, "pk", None))
            return {"stored": True, "id": getattr(obj, "pk", None), "mode": "minimal"}
        except Exception as e2:
            logger.exception("[store_post] Fallback save failed; giving up. Error=%s", e2)
            return {"stored": False, "id": None, "mode": "failed"}

# ----- View ------------------------------------------------------------------

@csrf_exempt
def store_post(request: HttpRequest) -> HttpResponse:
    """
    Endpoint consumed by WP admin.js after WordPress has created the post.

    Auth:
      - Primary: X-PPA-Key header must match settings.PPA_SHARED_KEY
      - OR: If request body is a sealed envelope {b64, ts, sig}, we verify HMAC and accept.

    Payload (after unsealing, if needed):
      - title (str), html (str), status (str), source (str: 'draft'|'publish'|'preview')
      - summary (str, optional), wp_post_id (int, optional)
      - token_usage (dict/list/str, optional)
      - target_sites (list[str], optional)
    """
    if request.method == "OPTIONS":
        return _options_response(request)

    if request.method != "POST":
        return _json({"ok": False, "error": "POST required"}, 405, request)

    expected_key = (getattr(settings, "PPA_SHARED_KEY", None) or os.getenv("PPA_SHARED_KEY") or "").strip()
    provided_key = (request.headers.get("X-PPA-Key") or request.META.get("HTTP_X_PPA_KEY") or "").strip()

    # Parse outer JSON — could be a normal payload or an envelope
    try:
        outer = json.loads((request.body or b"").decode("utf-8"))
    except Exception as e:
        logger.exception("[store_post] Invalid JSON")
        return _json({"ok": False, "error": f"Invalid JSON: {e}"}, 400, request)

    # Auth path A: header key
    header_auth_ok = bool(expected_key and provided_key and provided_key == expected_key)

    # Auth path B: sealed envelope
    envelope_auth_ok = False
    inner_payload = None
    if isinstance(outer, dict) and all(k in outer for k in ("b64","ts","sig")) and expected_key:
        inner_payload = _verify_and_unseal_envelope(outer, expected_key)
        envelope_auth_ok = inner_payload is not None

    logger.info(
        "[store_post] Auth check: header=%s envelope=%s",
        "ok" if header_auth_ok else "no",
        "ok" if envelope_auth_ok else "no",
    )

    if not header_auth_ok and not envelope_auth_ok:
        return _unauthorized(request, "auth_failed")

    # Use unsealed payload if present; otherwise expect normal payload
    payload = inner_payload if inner_payload is not None else outer

    # Target sites handling
    target_sites = payload.get("target_sites") or []
    if not isinstance(target_sites, list) or not target_sites:
        target_sites = [getattr(settings, "PPA_WP_API_URL", "")]
    first_target = target_sites[0] if target_sites else None
    logger.info("[store_post] Target sites: %s (using first=%s)", target_sites, first_target)

    # Validate required fields
    title = payload.get("title")
    html = payload.get("html")
    if not title or not html:
        logger.warning("[store_post] Missing required fields: title, html")
        return _json({"ok": False, "error": "Missing required fields: title, html"}, 400, request)

    status_val = payload.get("status", "draft")
    source_val = payload.get("source", "publish")
    token_usage = payload.get("token_usage") or {}

    logger.info(
        "[store_post] Payload: title=%r len(html)=%s status=%s source=%s token_usage=%s wp_post_id=%s",
        title,
        len(html) if isinstance(html, str) else "n/a",
        status_val,
        source_val,
        token_usage if isinstance(token_usage, (int, float, str)) else "(complex)",
        payload.get("wp_post_id"),
    )

    # Persist (safe + fallback)
    try:
        t0 = time.perf_counter()
        persist_result = _persist_article(payload, (time.perf_counter() - t0) * 1000)
        resp = {
            "ok": True,
            "stored": persist_result.get("stored", False),
            "id": persist_result.get("id"),
            "mode": persist_result.get("mode"),
            "request_ms": round((time.perf_counter() - t0) * 1000, 2),
            "target_used": first_target,
        }
        return _json(resp, 200, request)
    except Exception as e:
        # Absolute last-resort catch: never leak a 500 to client
        logger.exception("[store_post] Unexpected error: %s", e)
        out = {"ok": False, "error": "internal_error", "detail": "STORE failed; see server logs"}
        if getattr(settings, "DEBUG", False):
            out["diagnostic"] = {"exception": str(e)}
        return _json(out, 200, request)
