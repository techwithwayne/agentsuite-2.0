# -*- coding: utf-8 -*-
"""
CHANGE LOG
- 2025-08-15: Introduce _core.py with shared constants/helpers.                 # CHANGED:
    * Extracted VERSION, logger, CORS allowlist, auth helpers, JSON helpers,    # CHANGED:
      and preflight utility from views __init__ into a standalone module.       # CHANGED:
    * No behavior changes; not yet imported by other modules.                   # CHANGED:
    * This is step 1 of the granularization plan: each endpoint will move to    # CHANGED:
      its own module, while wrappers in views/__init__.py keep resolver stable. # CHANGED:
"""

from __future__ import annotations

import json  # CHANGED: required for _json_load
import logging  # CHANGED: consistent 'webdoctor' logger
import os  # CHANGED: env access for keys and UA
from typing import Any, Dict, Optional, Tuple  # CHANGED: type hints

from django.http import HttpRequest, HttpResponse, JsonResponse  # CHANGED:

# ----- constants -------------------------------------------------------------

# NOTE: Keep this in sync with the value used by existing endpoints until we    # CHANGED:
# wire all call sites to import from _core.                                     # CHANGED:
VERSION = "postpress-ai.v2.1-2025-08-14"  # CHANGED:

# Allowed origin for reflective CORS (minimal & strict, no wildcards).         # CHANGED:
_ALLOWED_ORIGINS = {
    "https://techwithwayne.com",  # primary WP site                            # CHANGED:
}

# Logger: consistent name so existing RotatingFileHandler continues to apply.  # CHANGED:
log = logging.getLogger("webdoctor")  # CHANGED:


# ----- helpers: auth, cors, json, contracts ---------------------------------

def _normalize_key(val: Optional[str]) -> str:
    """
    Normalize secret-like values for comparison without logging actual content.
    Strips wrapping quotes and CR/LF; trims whitespace.                         # CHANGED:
    """
    if val is None:
        return ""
    v = val.strip().strip("'").strip('"').replace("\r", "").replace("\n", "")
    return v  # CHANGED:


def _ppa_key_ok(request: HttpRequest) -> Tuple[bool, int, int, str]:
    """
    Validate X-PPA-Key header against PPA_SHARED_KEY in env.

    Returns:
        (match, expected_len, provided_len, origin_used)

    Logging hygiene: we log only lengths and the match flag; never the secret.  # CHANGED:
    """
    expected = _normalize_key(os.getenv("PPA_SHARED_KEY"))  # CHANGED:
    provided = _normalize_key(request.headers.get("X-PPA-Key"))  # CHANGED:
    match = (expected != "" and expected == provided)  # CHANGED:
    origin = request.headers.get("Origin", "") or ""  # CHANGED:

    # Structured hygiene logs; include URL name for easy grepping.              # CHANGED:
    try:
        url_name = request.resolver_match.url_name or "?"
    except Exception:
        url_name = "?"
    log.info(
        "[PPA][%s][auth] expected_len=%s provided_len=%s match=%s origin=%s",
        url_name, len(expected), len(provided), match, origin
    )  # CHANGED:

    return match, len(expected), len(provided), origin  # CHANGED:


def _allow_cors(resp: HttpResponse, origin: str) -> HttpResponse:
    """
    Reflect a known origin only. No wildcard; no credentials.                   # CHANGED:
    """
    if origin in _ALLOWED_ORIGINS:
        resp["Access-Control-Allow-Origin"] = origin  # CHANGED:
        resp["Vary"] = "Origin"  # CHANGED:
    return resp  # CHANGED:


def _cors_preflight_ok(request: HttpRequest) -> HttpResponse:
    """
    Minimal, strict CORS preflight response (204) for browser OPTIONS checks.   # CHANGED:
    Mirrors the needs of CF free tier; allowed headers are explicit.            # CHANGED:
    """
    origin = request.headers.get("Origin", "") or ""  # CHANGED:
    resp = HttpResponse(status=204)  # CHANGED:
    resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"  # CHANGED:
    resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key"  # CHANGED:
    resp["Access-Control-Max-Age"] = "600"  # CHANGED:
    return _allow_cors(resp, origin)  # CHANGED:


def _json_load(body: bytes) -> Tuple[bool, Dict[str, Any]]:
    """
    Parse JSON safely from request body.

    Returns:
        (ok, data_dict) — where ok=False yields an empty dict.                  # CHANGED:
    """
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
        return True, data if isinstance(data, dict) else {}
    except Exception:
        return False, {}  # CHANGED:


def _json_ok(data: Dict[str, Any], *, origin: str = "") -> JsonResponse:
    """
    Success JSON helper enforcing UTF-8 and applying strict CORS reflection.    # CHANGED:
    """
    resp = JsonResponse(data, status=200, json_dumps_params={"ensure_ascii": False})
    return _allow_cors(resp, origin)  # CHANGED:


def _json_fail(
    error: str,
    detail: Optional[str] = None,
    *,
    origin: str = "",
    status: int = 200,
) -> JsonResponse:
    """
    Failure JSON helper used by endpoints;                          # CHANGED:
    - /preview/: may use non-200 for method/auth errors             # CHANGED:
    - /store/: ALWAYS 200 by contract                               # CHANGED:
    """
    payload: Dict[str, Any] = {"ok": False, "error": error, "ver": VERSION}  # CHANGED:
    if detail:
        payload["detail"] = detail  # CHANGED:
    resp = JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})  # CHANGED:
    return _allow_cors(resp, origin)  # CHANGED:
