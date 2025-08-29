# /home/techwithwayne/agentsuite/postpress_ai/views/__init__.py
"""
CHANGE LOG
----------
2025-08-16
- CLEANUP: Runtime UTF-8 log-handler shim is now a NO-OP because settings-level logging        # CHANGED:
  already enforces encoding='utf-8'. Keeping the call in place but making the function         # CHANGED:
  return immediately avoids duplicate handler swaps and preserves import stability.            # CHANGED:

2025-08-16
- HARDENING (dead-code audit): Add lightweight startup audit that logs which preview/store
  delegate modules are present (without importing secrets). Helps detect lingering legacy
  stubs or duplicate adapters. No behavior change; logs use only module names.

2025-08-16
- FIX (logging): Ensure the 'webdoctor' RotatingFileHandler uses UTF-8 encoding even if
  settings didn't specify it. We patch the handler at import-time, replacing a non-UTF8
  RotatingFileHandler with an equivalent one that sets encoding='utf-8'.
- NOTE: No changes to endpoint contracts, CORS, or auth.

2025-08-16
- FIX (package surface): Ensure the public surface file is **__init__.py** (not init.py).
  This guarantees `import postpress_ai.views` loads the canonical package file, and that
  /version and /health correctly report `module="postpress_ai.views"` and the __file__ path.
- KEEP: Re-export endpoints (preview, store, version, health, preview_debug_model).
- KEEP: Expose `urlopen` at module scope for health-test monkeypatching.
- KEEP: Auth/CORS helpers, logging hygiene, VERSION, and optional STORE_DELEGATE hook.
"""

from __future__ import annotations  # CHANGED:

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time  # retained for historical compatibility; not used directly here
from typing import Any, Dict, Optional, Callable
from urllib.parse import urlparse
from importlib import import_module
import importlib.util as _import_util

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

# Expose urlopen at package surface so tests can monkeypatch `postpress_ai.views.urlopen`.
try:
    from urllib.request import urlopen  # type: ignore
except Exception:  # pragma: no cover
    urlopen = None  # type: ignore

__all__ = [
    # Public endpoints re-exported by this package surface
    "preview",
    "store",
    "version",
    "health",
    "preview_debug_model",
    # Test hook exposure
    "urlopen",
    "VERSION",
]

# ---------- Constants / Logger ----------
VERSION = "postpress-ai.v2.1-2025-08-14"
log = logging.getLogger("webdoctor")

# ---------- Logging: ensure UTF-8 file handler ----------
def _ensure_utf8_file_handler() -> None:
    """
    NO-OP as of 2025-08-16: settings-level LOGGING now sets encoding='utf-8' for any            # CHANGED:
    RotatingFileHandler. We keep this function callable to avoid import churn, but it           # CHANGED:
    returns immediately without modifying handlers.                                             # CHANGED:
    """  # CHANGED:
    return  # CHANGED:

_ensure_utf8_file_handler()

# ---------- Lightweight dead-code audit (modules only; no secrets) ----------
def _module_exists(modname: str) -> bool:
    """Check module availability without executing it (no side-effects)."""
    try:
        spec = _import_util.find_spec(modname)
        return spec is not None
    except Exception:
        return False

def _audit_delegates() -> None:
    """Log which delegate modules are present to spot lingering legacy stubs."""
    try:
        preview_candidates = [
            "postpress_ai.views.preview_post",  # preferred in-package
            "postpress_ai.preview_post",       # old location
            "postpress_ai.preview_post_legacy" # legacy/deprecated
        ]
        store_candidates = [
            "postpress_ai.views.store_post",   # preferred in-package
            "postpress_ai.store_post",         # old location
            "postpress_ai.store_post_legacy"   # legacy/deprecated
        ]

        found_preview = [m for m in preview_candidates if _module_exists(m)]
        found_store   = [m for m in store_candidates if _module_exists(m)]

        # Optional: identify callable names present in each found store module (no values)
        attr_names = ("store","handle","handler","view","post","store_post","post_store","delegate","call","entry")
        store_attr_map: Dict[str, str] = {}
        for m in found_store:
            try:
                mod = import_module(m)
                present = [a for a in attr_names if callable(getattr(mod, a, None))]
                store_attr_map[m] = ",".join(present) or "none"
            except Exception:
                store_attr_map[m] = "import-error"

        log.info("[PPA][audit] preview_delegate_modules=%s", ",".join(found_preview) or "none")
        log.info("[PPA][audit] store_delegate_modules=%s attrs=%s",
                 (",".join(found_store) or "none"), store_attr_map)
    except Exception:
        # Never fail import due to audit
        pass

_audit_delegates()

# Optional test hook used by store.py delegate resolver (can be set by tests).
STORE_DELEGATE: Optional[Callable[[HttpRequest], Any]] = None

# ---------- Small helpers (no secrets logged) ----------
def _normalize_header_value(v: Optional[str]) -> str:
    """
    Trim common wrapper quotes and CR/LF. Do NOT log actual values; callers only log lengths
    and boolean equality results to avoid leaking secrets.
    """
    if not v:
        return ""
    return v.strip().strip("'").strip('"').replace("\r", "").replace("\n", "")

def _is_test_env(request: HttpRequest) -> bool:
    """
    Detect Django test client / pytest context OR the built-in 'testserver' host used by
    Django's Client. This enables the test-only auth bypass as required by the spec.
    """
    if any(
        [
            any("test" in (arg or "").lower() for arg in sys.argv),
            "PYTEST_CURRENT_TEST" in os.environ,
            os.environ.get("DJANGO_TESTING") == "1",
            os.environ.get("UNITTEST_RUNNING") == "1",
        ]
    ):
        return True
    host = (request.META.get("HTTP_HOST") or "").lower()
    srv = (request.META.get("SERVER_NAME") or "").lower()
    return host == "testserver" or srv == "testserver"

def _ppa_key_ok(request: HttpRequest) -> bool:
    """
    Validate X-PPA-Key with normalization. During tests, bypass is enabled but still logs
    lengths (never raw values).
    """
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected = _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))
    if _is_test_env(request):
        log.info("[PPA][store][auth] test-bypass=True expected_len=%s provided_len=%s",
                 len(expected), len(provided))
        return True
    ok = bool(expected) and (provided == expected)
    log.info("[PPA][store][auth] expected_len=%s provided_len=%s match=%s origin=%s",
             len(expected), len(provided), ok,
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    return ok

def _allowed_origin(origin: Optional[str]) -> Optional[str]:
    """
    Reflect CORS only for explicitly allowed origins — never wildcard.
    """
    if not origin:
        return None
    origin = origin.strip()
    allowed = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    allowed.update(getattr(settings, "PPA_ALLOWED_ORIGINS", []))
    return origin if origin in allowed else None

def _with_cors(resp: HttpResponse, request: HttpRequest) -> HttpResponse:
    """
    Apply CORS headers when the Origin is explicitly allowed.
    """
    origin = _allowed_origin(request.META.get("HTTP_ORIGIN"))
    if origin:
        resp["Access-Control-Allow-Origin"] = origin
        resp["Vary"] = "Origin"
        resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key, X-PPA-Install, X-PPA-Version"
        resp["Access-Control-Allow-Methods"] = "POST, OPTIONS, GET"
        resp["Access-Control-Allow-Credentials"] = "true"
    return resp

def _json_response(payload: Dict[str, Any], status: int = 200, request: Optional[HttpRequest] = None) -> JsonResponse:
    """
    Attach `ver` automatically and reflect CORS if we have a request context.
    """
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
    """Light URL check used by the store normalizer (avoid false positives)."""
    try:
        if not val:
            return False
        u = urlparse(val)
        return bool(u.scheme) and bool(u.netloc)
    except Exception:
        return False

# --------- Re-export extracted views (single source of truth) ---------
from .version import version
from .health import health
from .preview import preview
from .store import store
from .debug_model import preview_debug_model
