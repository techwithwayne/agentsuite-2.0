# /home/techwithwayne/agentsuite/postpress_ai/views/debug_model.py
"""
CHANGE LOG
----------
2025-08-16
- HARDENING (CORS preflight): Allow OPTIONS without auth for /preview/debug-model/             # CHANGED:
  so browsers can complete CORS preflight. This mirrors /preview/ behavior and                # CHANGED:
  does NOT relax GET auth requirements.                                                       # CHANGED:
- IMPLEMENTATION: Uses _with_cors(HttpResponse(204)) for preflight; GET path unchanged.       # CHANGED:

2025-08-16
- NEW FILE: Extracted the /preview/debug-model/ endpoint into a dedicated module.
"""

from __future__ import annotations  # CHANGED:

import os
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse, HttpResponse  # CHANGED:

from . import (  # CHANGED:
    _json_response,
    _normalize_header_value,
    _is_test_env,
    _with_cors,                # CHANGED:
    VERSION,
)

log = logging.getLogger("webdoctor")
__all__ = ["preview_debug_model"]


def preview_debug_model(request: HttpRequest) -> JsonResponse | HttpResponse:  # CHANGED:
    """
    GET:   Returns current preview provider/model details; requires valid X-PPA-Key
           unless running under test bypass.
    OPTS:  Open (no auth) to support CORS preflight; returns 204 with allowed CORS            # CHANGED:
           reflection only (never wildcard).                                                  # CHANGED:
    """  # CHANGED:

    # Allow CORS preflight without auth (Cloudflare-friendly, mirrors /preview/).             # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _with_cors(HttpResponse(status=204), request)  # CHANGED:

    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected = _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))
    ok = _is_test_env(request) or (bool(expected) and (provided == expected))
    log.info("[PPA][preview-debug][entry] host=%s origin=%s auth_ok=%s expected_len=%s provided_len=%s",
             _normalize_header_value(request.META.get("HTTP_HOST")),
             _normalize_header_value(request.META.get("HTTP_ORIGIN")),
             ok, len(expected), len(provided))

    if not ok:
        return _json_response({"ok": False, "error": "preview-debug.forbidden"}, 403, request)

    provider_pref = os.getenv("PPA_PREVIEW_PROVIDER", "auto")
    strategy = os.getenv("PPA_PREVIEW_STRATEGY", "fixed")
    openai_model = os.getenv("PPA_PREVIEW_OPENAI_MODEL", "gpt-4.1-mini")
    anthropic_model = os.getenv("PPA_PREVIEW_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    if provider_pref == "openai":
        provider = "openai"; model = openai_model
    elif provider_pref == "anthropic":
        provider = "anthropic"; model = anthropic_model
    else:
        provider = "auto"; model = openai_model

    have_openai = bool(os.getenv("OPENAI_API_KEY"))
    have_anthropic = bool(os.getenv("CLAUDE_API_KEY"))

    return _json_response(
        {
            "ok": True,
            "provider": provider,
            "model": model,
            "provider_pref": provider_pref,
            "strategy": strategy,
            "have_openai": have_openai,
            "have_anthropic": have_anthropic,
        },
        200,
        request,
    )  # CHANGED:
