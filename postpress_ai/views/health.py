# /home/techwithwayne/agentsuite/postpress_ai/views/health.py
"""
CHANGE LOG
----------
2025-08-17
- ENHANCEMENT: Handle CORS preflight (OPTIONS) explicitly with 204 + CORS reflection.          # CHANGED:
- FIX: If PPA_WP_API_URL is empty or invalid, return early with                              # CHANGED:
       wp_reachable=False, wp_allowed=False, wp_status="unreachable", wp_error="url-error".   # CHANGED:
       (Aligns behavior with Ops Runbook and avoids misleading timeouts.)                     # CHANGED:
- HOTFIX: Return **204** (empty) for OPTIONS instead of 200 JSON to satisfy tests and         # CHANGED:
          match other endpoints' preflight behavior.                                          # CHANGED:

2025-08-16
- FIX (contract compatibility): module="postpress_ai.views"; file points to public
  surface (__init__.py).
- FIX (monkeypatch): Resolve package-level `urlopen` at call time from postpress_ai.views.
- NEW FILE: Extracted the /health/ endpoint into a dedicated module.
"""

from __future__ import annotations  # CHANGED:

import os
import logging
from typing import Any, Optional
from importlib import import_module

from django.conf import settings
from django.http import HttpRequest, JsonResponse, HttpResponse  # CHANGED:

from . import _json_response, _normalize_header_value, VERSION, _is_url, _with_cors  # CHANGED:

log = logging.getLogger("webdoctor")
__all__ = ["health"]

def _extract_status(obj: Any) -> int:
    for attr in ("status", "code"):
        v = getattr(obj, attr, None)
        try:
            if v is None:
                continue
            return int(v)
        except Exception:
            continue
    getcode = getattr(obj, "getcode", None)
    if callable(getcode):
        try:
            return int(getcode())
        except Exception:
            pass
    return 0

def _get_package_urlopen():
    try:
        pkg = import_module("postpress_ai.views")
        return getattr(pkg, "urlopen", None)
    except Exception:
        return None

def _canonical_views_init_path() -> str:
    try:
        pkg = import_module("postpress_ai.views")
        p = getattr(pkg, "__file__", __file__)
        return str(p)
    except Exception:
        return __file__

def health(request: HttpRequest) -> JsonResponse | HttpResponse:
    # Always answer preflight with 204 (empty) and reflect CORS                               # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _with_cors(HttpResponse(status=204), request)  # CHANGED:
    if request.method != "GET":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    base = getattr(settings, "PPA_WP_API_URL", "").rstrip("/")
    ua = getattr(settings, "PPA_HEALTH_UA", "Mozilla/5.0")
    timeout_s = float(os.getenv("PPA_HEALTH_TIMEOUT_SECONDS", "1"))

    # Early-return when URL is missing or malformed (per runbook semantics).
    if not base or not _is_url(base):
        payload = {
            "ok": True,
            "module": "postpress_ai.views",
            "file": _canonical_views_init_path(),
            "wp_base": base,
            "wp_reachable": False,
            "wp_allowed": False,
            "wp_status": "unreachable",
            "wp_error": "url-error",
            "ua_used": ua,
            "ver": VERSION,
        }
        return _json_response(payload, 200, request)

    reachable = False
    allowed = False
    wp_status: Any = "unreachable"
    wp_error: Optional[str] = None

    try:
        urlopen = _get_package_urlopen()
        if urlopen is None:
            raise RuntimeError("no-urlopen")

        import urllib.request as _req
        req = _req.Request(base, headers={"User-Agent": ua})
        try:
            resp_ctx = urlopen(req, timeout=timeout_s)  # type: ignore
        except TypeError:
            resp_ctx = urlopen(req)  # type: ignore

        if hasattr(resp_ctx, "__enter__"):
            with resp_ctx as r:
                code = _extract_status(r)
        else:
            r = resp_ctx
            code = _extract_status(r)

        wp_status = int(code)
        reachable = True
        allowed = 200 <= wp_status < 400

    except __import__("urllib.error").error.HTTPError as e:
        wp_status = int(e.code)
        reachable = True
        allowed = 200 <= wp_status < 400
        wp_error = "http-error"

    except __import__("urllib.error").error.URLError:
        wp_status = "unreachable"
        wp_error = "url-error"

    except Exception:
        wp_status = "timeout"
        wp_error = "timeout"

    payload = {
        "ok": True,
        "module": "postpress_ai.views",
        "file": _canonical_views_init_path(),
        "wp_base": base,
        "wp_reachable": reachable,
        "wp_allowed": allowed,
        "wp_status": wp_status,
        "wp_error": wp_error,
        "ua_used": ua,
        "ver": VERSION,
    }
    return _json_response(payload, 200, request)
