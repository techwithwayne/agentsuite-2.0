"""
/preview/ endpoint
"""

from __future__ import annotations

import logging
import json
import os
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .utils import _json_response, _normalize_header_value, _ppa_key_ok, _with_cors, VERSION

log = logging.getLogger("webdoctor")
__all__ = ["preview"]

try:
    from . import preview_post as _pp  # type: ignore
except Exception:  # pragma: no cover
    _pp = None

def _truthy_env(name: str) -> bool:
    """Return True if environment variable is a common truthy value."""
    val = (os.getenv(name) or "").strip().lower()
    return val in {"1", "true", "yes", "force"}

def _log_preview_auth(request: HttpRequest) -> None:
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected_len = 0
    try:
        from django.conf import settings
        expected = _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))
        expected_len = len(expected)
        match = bool(expected) and (provided == expected)
    except Exception:
        match = False
    log.info("[PPA][preview][auth] expected_len=%s provided_len=%s match=%s origin=%s",
             expected_len, len(provided), match, _normalize_header_value(request.META.get("HTTP_ORIGIN")))

def _local_fallback_success_payload() -> dict[str, Any]:
    """Deterministic local preview per spec when provider misbehaves or is down."""
    return {
        "ok": True,
        "result": {
            "title": "PostPress AI Preview (Provider Fallback)",
            "html": "<p>Preview not available; provider offline.</p><!-- provider: local-fallback -->",
            "summary": "Local fallback summary.",
        },
        "ver": VERSION,
    }

@csrf_exempt
def preview(request: HttpRequest) -> JsonResponse | HttpResponse:
    log.info("[PPA][preview][entry] host=%s origin=%s",
             _normalize_header_value(request.META.get("HTTP_HOST")),
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    _log_preview_auth(request)

    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)

    # Operator drill: force local fallback
    if _truthy_env("PPA_PREVIEW_FORCE_FALLBACK"):
        if request.method != "POST":
            return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)
        if not _ppa_key_ok(request):
            return _json_response({"ok": False, "error": "forbidden"}, 403, request)
        return _json_response(_local_fallback_success_payload(), 200, request)

    # If a provider delegate exists, hand off immediately
    if _pp and hasattr(_pp, "preview"):
        try:
            delegate_resp: HttpResponse = _pp.preview(request)  # type: ignore
            return delegate_resp
        except Exception as exc:
            log.exception("[PPA][preview][delegate_crash] %s", exc)
            return _json_response(_local_fallback_success_payload(), 200, request)

    # Local wrapper behavior (only runs if provider module is absent)
    if request.method != "POST":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    # Enforce X-PPA-Key on the fallback path
    if not _ppa_key_ok(request):
        return _json_response({"ok": False, "error": "forbidden"}, 403, request)

    return _json_response(_local_fallback_success_payload(), 200, request)
