# /home/techwithwayne/agentsuite/postpress_ai/views/version.py
"""
CHANGE LOG
----------
2025-08-16
- HARDENING (CORS preflight): Allow OPTIONS without auth for /version/ so browsers              # CHANGED:
  can complete CORS preflight. Mirrors other endpoints; does NOT change GET behavior.          # CHANGED:
- IMPLEMENTATION: Use _with_cors(HttpResponse(204)) for OPTIONS; GET path unchanged.           # CHANGED:

2025-08-16
- FIX (contract compatibility): module="postpress_ai.views"; file points to the
  canonical public surface (__init__.py), not this file.
- NEW FILE: Extracted the /version/ endpoint into a dedicated module.
"""

from __future__ import annotations  # CHANGED:

import logging
import time
from importlib import import_module

from django.http import HttpRequest, JsonResponse, HttpResponse  # CHANGED:

from . import (  # CHANGED:
    _json_response,
    _normalize_header_value,
    VERSION,
)  # CHANGED:
from . import _with_cors  # CHANGED:

log = logging.getLogger("webdoctor")
__all__ = ["version"]


def _canonical_views_init_path() -> str:
    """
    Resolve the path to the canonical package surface file so tests see                        # CHANGED:
    file=.../postpress_ai/views/__init__.py (not this module).                                 # CHANGED:
    """
    try:
        pkg = import_module("postpress_ai.views")
        p = getattr(pkg, "__file__", __file__)
        return str(p)
    except Exception:
        return __file__


def version(request: HttpRequest) -> JsonResponse | HttpResponse:  # CHANGED:
    """
    GET: Returns the current version payload.                                                  # CHANGED:
    OPTIONS: Open (no auth) to support CORS preflight; returns 204 with CORS reflection.       # CHANGED:
    """  # CHANGED:
    log.info(
        "[PPA][version][entry] host=%s origin=%s",
        _normalize_header_value(request.META.get("HTTP_HOST")),
        _normalize_header_value(request.META.get("HTTP_ORIGIN")),
    )
    # CORS preflight should be accepted without auth and with reflected origin.                # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _with_cors(HttpResponse(status=204), request)  # CHANGED:

    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    payload = {
        "ok": True,
        "ver": VERSION,
        "build_time": str(int(time.time())),
        "module": "postpress_ai.views",       # must be package surface, not this file         # CHANGED:
        "file": _canonical_views_init_path(), # points to .../postpress_ai/views/__init__.py   # CHANGED:
    }
    # _json_response will add CORS reflection (if Origin allowed) while preserving shape.      # CHANGED:
    return _json_response(payload, 200, request)
