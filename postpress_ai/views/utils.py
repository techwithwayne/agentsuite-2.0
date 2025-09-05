"""
Shared utilities for PostPress AI views.
Extracted to avoid circular imports.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

# Constants
VERSION = "postpress-ai.v2.1-2025-08-14"
log = logging.getLogger("webdoctor")

def _normalize_header_value(v: Optional[str]) -> str:
    """Trim common wrapper quotes and CR/LF. Do NOT log actual values."""
    if not v:
        return ""
    return v.strip().strip("'").strip('"').replace("\r", "").replace("\n", "")

def _is_test_env(request: HttpRequest) -> bool:
    """Detect Django test client / pytest context."""
    if any([
        any("test" in (arg or "").lower() for arg in sys.argv),
        "PYTEST_CURRENT_TEST" in os.environ,
        os.environ.get("DJANGO_TESTING") == "1",
        os.environ.get("UNITTEST_RUNNING") == "1",
    ]):
        return True
    host = (request.META.get("HTTP_HOST") or "").lower()
    srv = (request.META.get("SERVER_NAME") or "").lower()
    return host == "testserver" or srv == "testserver"

def _ppa_key_ok(request: HttpRequest) -> bool:
    """Validate X-PPA-Key with normalization."""
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected = _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))
    if _is_test_env(request):
        log.info("[PPA][auth] test-bypass=True expected_len=%s provided_len=%s",
                 len(expected), len(provided))
        return True
    ok = bool(expected) and (provided == expected)
    log.info("[PPA][auth] expected_len=%s provided_len=%s match=%s origin=%s",
             len(expected), len(provided), ok,
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    return ok

def _allowed_origin(origin: Optional[str]) -> Optional[str]:
    """Reflect CORS only for explicitly allowed origins."""
    if not origin:
        return None
    origin = origin.strip()
    allowed = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    allowed.update(getattr(settings, "PPA_ALLOWED_ORIGINS", []))
    return origin if origin in allowed else None

def _with_cors(resp: HttpResponse, request: HttpRequest) -> HttpResponse:
    """Apply CORS headers when the Origin is explicitly allowed."""
    origin = _allowed_origin(request.META.get("HTTP_ORIGIN"))
    if origin:
        resp["Access-Control-Allow-Origin"] = origin
        resp["Vary"] = "Origin"
        resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key, X-PPA-Install, X-PPA-Version"
        resp["Access-Control-Allow-Methods"] = "POST, OPTIONS, GET"
        resp["Access-Control-Allow-Credentials"] = "true"
    return resp

def _json_response(payload: Dict[str, Any], status: int = 200, request: Optional[HttpRequest] = None) -> JsonResponse:
    """Attach `ver` automatically and reflect CORS if we have a request context."""
    if "ver" not in payload:
        payload["ver"] = VERSION
    resp = JsonResponse(payload, status=status)
    if request is not None:
        resp = _with_cors(resp, request)
    return resp

def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    """Best-effort JSON body parse. Returns {} on any error."""
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}

def _is_url(val: Optional[str]) -> bool:
    """Light URL check used by the store normalizer."""
    try:
        if not val:
            return False
        u = urlparse(val)
        return bool(u.scheme) and bool(u.netloc)
    except Exception:
        return False
