"""
/version/ endpoint
"""

from __future__ import annotations

import logging
import time
from importlib import import_module

from django.http import HttpRequest, JsonResponse, HttpResponse

from .utils import _json_response, _normalize_header_value, VERSION, _with_cors

log = logging.getLogger("webdoctor")
__all__ = ["version"]

def _canonical_views_init_path() -> str:
    """Resolve the path to the canonical package surface file."""
    try:
        pkg = import_module("postpress_ai.views")
        p = getattr(pkg, "__file__", __file__)
        return str(p)
    except Exception:
        return __file__

def version(request: HttpRequest) -> JsonResponse | HttpResponse:
    """
    GET: Returns the current version payload.
    OPTIONS: Open (no auth) to support CORS preflight.
    """
    log.info("[PPA][version][entry] host=%s origin=%s",
             _normalize_header_value(request.META.get("HTTP_HOST")),
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    
    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)

    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    payload = {
        "ok": True,
        "ver": VERSION,
        "build_time": str(int(time.time())),
        "module": "postpress_ai.views",
        "file": _canonical_views_init_path(),
    }
    return _json_response(payload, 200, request)
