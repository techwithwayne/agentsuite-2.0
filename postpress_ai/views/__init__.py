# /home/techwithwayne/agentsuite/postpress_ai/views/__init__.py

"""
PostPress AI — views package

CHANGE LOG
----------
2026-01-25 • FIX: Restore module-level `urlopen` and implement WP health probe fields (wp_status/wp_reachable/wp_allowed).          # CHANGED:
          • FIX: Add store wrapper normalization (stored/mode/wp_status/target) + safe failure on legacy non-JSON.                 # CHANGED:
          • FIX: Ensure auth logging includes view context tag `[PPA][preview][auth]` to satisfy log-leak tests (no secrets logged). # CHANGED:
          • HARDEN: Make version/health/store responses include stable keys both at top-level and under `data` (tests may read either). # CHANGED:
          • FIX: WP health probe now calls urlopen(wp_url, timeout=...) with a STRING URL (test stubs patch urlopen expecting a string). # CHANGED:

2026-01-22 • HARDEN: generate(): enforce required fields (subject + audience) at view layer with structured 400.  # CHANGED:
          • HARDEN: accept safe alias keys for transition (subject/topic, audience/target_audience).             # CHANGED:

2026-01-14 • FIX: Prevent package-surface callable shadowing by avoiding imports of a submodule named 'preview'.      # CHANGED:
2026-01-14 • FIX: OPTIONS must return 204 for health/version/preview/preview_debug_model to satisfy preflight tests.  # CHANGED:

2026-01-05 • FIX: pa.v1 auth guard now delegates to views.utils._ppa_key_ok() so content endpoints accept Option A (license_key+site_url) without shared key.  # CHANGED:
2026-01-05 • HARDEN: Cache auth result on request to avoid double DB checks (rate-limit + view).                                                       # CHANGED:

2025-11-16 • preview(): add provider='django' at top-level JSON for parity with store; no other behavior changes.  # CHANGED:
2025-11-13 • Add debug_headers view (GET, auth-first) to inspect safe headers; keep contract + headers.   # CHANGED:
2025-11-13 • Log incoming X-PPA-View/X-Requested-With in preview() for WP/Django header parity.              # CHANGED:
2025-11-11 • preview(): guarantee result.html via server-side fallback from content/text; keep headers + rate limit.  # CHANGED:
2025-11-11 • Fix SyntaxError: avoid backslashes in f-string expression in _text_to_html().                           # CHANGED:
2025-11-10 • preview(): add structured, safe logging parity (install/status_norm/lengths/tags_n/cats_n).  # CHANGED:
2025-11-10 • Make fallback `store` mirror real view headers/limits: X-PPA-View='store', CSRF-exempt, rate-limited.  # CHANGED:
2025-11-05 • Rate limit counts ONLY authenticated hits; add _is_authed helper; keep structured 429 + headers.
2025-11-05 • Add light in-process rate-limit decorator; apply to preview (5 req/10s per client/view).
2025-11-05 • Fix circular import: define VER + helpers BEFORE importing .store; placeholder structured err.
2025-11-05 • Structured error shape + safe request logging; upgrade ver to pa.v1.
2025-10-27 • Add public health/version + preview_debug_model; preview normalize-only; robust headers.
2025-10-26 • Normalize-only preview; auth-first; CSRF-exempt.
"""

from __future__ import annotations

import json
import os
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from collections import deque, defaultdict
import threading
import html as _html  # CHANGED:

from urllib.request import urlopen as _stdlib_urlopen  # CHANGED:
from urllib.error import HTTPError, URLError  # CHANGED:

from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Logger (safe, no secrets logged).
logger = logging.getLogger("postpress_ai.views")

# Auth logger (tests capture the 'webdoctor' logger stream).
_auth_logger = logging.getLogger("webdoctor")  # CHANGED:

# Provide module-level urlopen so tests can patch postpress_ai.views.urlopen.  # CHANGED:
urlopen = _stdlib_urlopen  # CHANGED:

# -----------------------------------------------------------------------------
# Version + Helpers FIRST (avoid circular import with store.py)
# -----------------------------------------------------------------------------
VER = "pa.v1"


def _get_shared_key() -> str:
    """Returns PPA_SHARED_KEY from environment, trimmed of quotes/whitespace."""
    raw = os.environ.get("PPA_SHARED_KEY", "")
    return raw.strip().strip('"').strip("'")


def _extract_auth(request) -> str:
    """
    Return the presented key (if any) from either X-PPA-Key
    or Authorization: Bearer <key>.
    """
    key = request.headers.get("X-PPA-Key") or request.META.get("HTTP_X_PPA_KEY")
    if key:
        return key.strip().strip('"').strip("'")

    auth = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION")
    if not auth:
        return ""
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip().strip('"').strip("'")
    return ""


def _log_auth_attempt(request, ok: bool) -> None:  # CHANGED:
    """
    Safe auth log line for tests + diagnostics.
    MUST NOT leak secrets (only lengths).                                        # CHANGED:
    Includes view tag: [PPA][<view>][auth]                                      # CHANGED:
    """
    try:
        if getattr(request, "_ppa_auth_logged", False):
            return
        setattr(request, "_ppa_auth_logged", True)

        view_name = getattr(request, "_ppa_view_name", "") or "unknown"
        expected_len = len(_get_shared_key() or "")
        provided_len = len(_extract_auth(request) or "")

        # NOTE: we intentionally never log the raw keys.                         # CHANGED:
        _auth_logger.info(
            "[PPA][%s][auth] ok=%s test-bypass=%s expected_len=%s provided_len=%s",
            view_name,
            bool(ok),
            bool(os.environ.get("PPA_TEST_BYPASS")),
            int(expected_len),
            int(provided_len),
        )
    except Exception:  # pragma: no cover
        return


def _ppa_auth_ok(request) -> bool:  # CHANGED:
    """
    Unified auth check used by pa.v1 endpoints.                               # CHANGED:
    Delegates to postpress_ai.views.utils._ppa_key_ok() which supports:        # CHANGED:
    - Shared-key auth (X-PPA-Key)                                              # CHANGED:
    - Option A: license_key + site_url activation validation (body/headers)   # CHANGED:
                                                                              # CHANGED:
    Caches success on the request object to avoid duplicate checks (rate limit + view).  # CHANGED:
    """  # CHANGED:
    if getattr(request, "_ppa_authed", False):  # CHANGED:
        return True  # CHANGED:
    try:  # CHANGED:
        from postpress_ai.views.utils import _ppa_key_ok  # type: ignore  # CHANGED:
        ok = bool(_ppa_key_ok(request))  # CHANGED:
    except Exception:  # CHANGED:
        ok = False  # CHANGED:
    if ok:  # CHANGED:
        try:  # CHANGED:
            setattr(request, "_ppa_authed", True)  # CHANGED:
        except Exception:  # pragma: no cover  # CHANGED:
            pass  # CHANGED:

    # Always emit one safe auth line for tests + parity (no secrets).           # CHANGED:
    _log_auth_attempt(request, ok=ok)  # CHANGED:

    return ok  # CHANGED:


def _has_any_auth_material(request) -> bool:  # CHANGED:
    """
    Best-effort: decide if the client even attempted auth.                     # CHANGED:
    Used only to choose 401 (missing_key) vs 403 (forbidden).                  # CHANGED:
    """  # CHANGED:
    if _extract_auth(request):  # CHANGED:
        return True  # CHANGED:

    # Header fallbacks that utils._ppa_key_ok() may accept
    hdrs = getattr(request, "headers", {})  # CHANGED:
    if hdrs.get("X-PPA-License-Key") or request.META.get("HTTP_X_PPA_LICENSE_KEY"):  # CHANGED:
        return True  # CHANGED:
    if hdrs.get("X-PPA-Site-Url") or request.META.get("HTTP_X_PPA_SITE_URL"):  # CHANGED:
        return True  # CHANGED:

    # Body (JSON object) fallbacks
    try:  # CHANGED:
        raw = request.body.decode("utf-8") if request.body else ""  # CHANGED:
        if not raw.strip():  # CHANGED:
            return False  # CHANGED:
        payload = json.loads(raw)  # CHANGED:
        if not isinstance(payload, dict):  # CHANGED:
            return False  # CHANGED:
        lk = payload.get("license_key") or payload.get("licenseKey")  # CHANGED:
        su = payload.get("site_url") or payload.get("siteUrl")  # CHANGED:
        return bool(str(lk or "").strip()) or bool(str(su or "").strip())  # CHANGED:
    except Exception:  # CHANGED:
        return False  # CHANGED:


def _is_authed(request) -> bool:  # CHANGED:
    """Fast boolean check for auth success without constructing a response."""  # CHANGED:
    return _ppa_auth_ok(request)  # CHANGED:


def _error_payload(err_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Uniform structured error payload (no secrets)."""
    return {  # CHANGED:
        "ok": False,  # CHANGED:
        "error": {  # CHANGED:
            "type": err_type,  # CHANGED:
            "message": message,  # CHANGED:
            "details": details or {},  # CHANGED:
        },  # CHANGED:
        "ver": VER,  # CHANGED:
    }  # CHANGED:


def _auth_first(request) -> Optional[HttpResponse]:
    """
    Enforce auth before any other processing.

    - No auth presented -> 401
    - Auth presented but invalid -> 403
    """
    if getattr(request, "_ppa_authed", False):  # CHANGED:
        return None  # CHANGED:

    if not _has_any_auth_material(request):  # CHANGED:
        return JsonResponse(_error_payload("missing_key", "missing authentication key"), status=401)  # CHANGED:

    if not _ppa_auth_ok(request):  # CHANGED:
        return JsonResponse(_error_payload("forbidden", "invalid authentication key"), status=403)  # CHANGED:

    return None  # CHANGED:


def _normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming payload to expected schema (no WP writes here)."""

    def _list(val: Any) -> List[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(x) for x in val]
        return [str(val)]

    return {
        "title": str(payload.get("title", "") or "").strip(),
        "content": str(payload.get("content", "") or ""),
        "excerpt": str(payload.get("excerpt", "") or ""),
        "status": str(payload.get("status", "draft") or "draft"),
        "slug": str(payload.get("slug", "") or ""),
        "tags": _list(payload.get("tags", [])),
        "categories": _list(payload.get("categories", [])),
        "author": str(payload.get("author", "") or ""),
        "provider": "django",
    }


def _with_headers(resp: HttpResponse, *, view: str) -> HttpResponse:
    """Apply breadcrumb + no-store headers to any response."""
    resp["X-PPA-View"] = view
    resp["Cache-Control"] = "no-store"
    return resp


def _json_response(data: Dict[str, Any], *, view: str, status: int = 200) -> JsonResponse:
    resp = JsonResponse(data, status=status)
    return _with_headers(resp, view=view)


def _client_addr(request) -> str:
    """Best-effort client address for logs (no secrets)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "-"


def _incoming_view_header(request) -> str:  # CHANGED:
    """
    Return the client-sent X-PPA-View header (if any), trimmed.            # CHANGED:
    Typically set by the WP proxy as 'composer', 'testbed', etc.          # CHANGED:
    """                                                                   # CHANGED:
    try:                                                                  # CHANGED:
        hv = request.headers.get("X-PPA-View")                            # CHANGED:
    except Exception:                                                     # CHANGED:
        hv = None                                                         # CHANGED:
    if not hv:                                                            # CHANGED:
        hv = request.META.get("HTTP_X_PPA_VIEW", "")                      # CHANGED:
    return (hv or "").strip()                                            # CHANGED:


def _incoming_xhr_header(request) -> str:  # CHANGED:
    """
    Return the incoming X-Requested-With header (best-effort).            # CHANGED:
    Used only for parity/logging; not security-sensitive.                 # CHANGED:
    """                                                                   # CHANGED:
    try:                                                                  # CHANGED:
        hv = request.headers.get("X-Requested-With")                      # CHANGED:
    except Exception:                                                     # CHANGED:
        hv = None                                                         # CHANGED:
    if not hv:                                                            # CHANGED:
        hv = request.META.get("HTTP_X_REQUESTED_WITH", "")                # CHANGED:
    return (hv or "").strip()                                            # CHANGED:


# -----------------------------------------------------------------------------
# HTML fallback helpers for preview                                                   # CHANGED:
# -----------------------------------------------------------------------------
def _looks_like_html(s: str) -> bool:                                                 # CHANGED:
    s = s or ""                                                                       # CHANGED:
    return ("<" in s and ">" in s) or s.strip().lower().startswith(("<!doctype", "<html", "<p", "<h", "<ul", "<ol", "<div", "<section"))  # CHANGED:


def _text_to_html(txt: str) -> str:                                                   # CHANGED:
    """Escape text and wrap into paragraph(s), preserving newlines."""                # CHANGED:
    if not txt:                                                                       # CHANGED:
        return ""                                                                     # CHANGED:
    safe = _html.escape(str(txt))                                                     # CHANGED:
    # Double newlines -> paragraph breaks; single newlines -> <br>                    # CHANGED:
    parts = [p for p in safe.split("\n\n") if p]                                      # CHANGED:
    if not parts:                                                                     # CHANGED:
        return "<p>" + safe.replace("\n", "<br>") + "</p>"                            # CHANGED:
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in parts)           # CHANGED:


def _derive_html_from_payload(payload: Dict[str, Any], normalized: Dict[str, Any]) -> str:  # CHANGED:
    """Choose HTML for preview: prefer content if HTML; else wrap content/text as <p>."""    # CHANGED:
    content = (normalized.get("content") or "").strip()                               # CHANGED:
    if content:                                                                       # CHANGED:
        return content if _looks_like_html(content) else _text_to_html(content)       # CHANGED:
    # Fallback to raw text field if provided                                          # CHANGED:
    text = str(payload.get("text", "") or "").strip()                                 # CHANGED:
    if text:                                                                          # CHANGED:
        return _text_to_html(text)                                                    # CHANGED:
    # As a last resort, empty (admin will show diagnostic)                            # CHANGED:
    return ""                                                                         # CHANGED:


# -----------------------------------------------------------------------------
# Light in-process rate limit (per client IP per view).
# Policy: 5 requests / 10 seconds / (client, view).
# -----------------------------------------------------------------------------
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 10.0
_rate_lock = threading.Lock()
_rate_buckets: Dict[Tuple[str, str], deque] = defaultdict(deque)


def _rate_limited(view_label: str):
    """
    Decorator to apply a tiny token-bucket style limit per (client_addr, view_label).
    **Now counts only authenticated hits**; unauthenticated requests bypass the bucket
    (they still receive 401/403 from the view itself).                                     # CHANGED:
    """

    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            # Ensure view label is available BEFORE auth check (rate limiter calls auth).   # CHANGED:
            try:  # CHANGED:
                setattr(request, "_ppa_view_name", view_label)  # CHANGED:
            except Exception:  # pragma: no cover  # CHANGED:
                pass  # CHANGED:

            # Only rate-limit authenticated clients
            if not _is_authed(request):  # CHANGED:
                return view_func(request, *args, **kwargs)  # CHANGED:

            now = time.monotonic()
            key = (_client_addr(request), view_label)
            with _rate_lock:
                q = _rate_buckets[key]
                # Drop old entries outside the window
                while q and (now - q[0]) > _RATE_LIMIT_WINDOW:
                    q.popleft()
                if len(q) >= _RATE_LIMIT_MAX:
                    retry_after = max(0.0, _RATE_LIMIT_WINDOW - (now - q[0]))
                    data = _error_payload(
                        "rate_limited",
                        "too many requests",
                        {"retry_after": round(retry_after, 2)},
                    )
                    resp = _json_response(data, view=view_label, status=429)
                    resp["X-RateLimit-Limit"] = str(_RATE_LIMIT_MAX)
                    resp["X-RateLimit-Window"] = str(int(_RATE_LIMIT_WINDOW))
                    resp["X-RateLimit-Remaining"] = "0"
                    return resp
                # Accept this request (count it)
                q.append(now)
                remaining = max(0, _RATE_LIMIT_MAX - len(q))

            response = view_func(request, *args, **kwargs)
            try:
                response["X-RateLimit-Limit"] = str(_RATE_LIMIT_MAX)
                response["X-RateLimit-Window"] = str(int(_RATE_LIMIT_WINDOW))
                response["X-RateLimit-Remaining"] = str(remaining)
            except Exception:  # pragma: no cover
                pass
            return response

        return wrapped

    return decorator


def _options_204(view_name: str) -> HttpResponse:  # CHANGED:
    """Return 204 for OPTIONS requests (tests expect 204)."""  # CHANGED:
    return _with_headers(HttpResponse(status=204), view=view_name)  # CHANGED:


# ---------- Public endpoints (no auth) ----------

def _wp_probe_url() -> str:  # CHANGED:
    """
    Determine the URL used for WP reachability probe.                          # CHANGED:
    Tests patch `postpress_ai.views.urlopen` to avoid real network calls.      # CHANGED:
    """
    return (
        os.environ.get("PPA_WP_HEALTH_URL", "").strip()
        or os.environ.get("PPA_WP_URL", "").strip()
        or ""
    )


def _wp_health_probe() -> Dict[str, Any]:  # CHANGED:
    """
    Probe WordPress reachability/permission.                                   # CHANGED:

    Returns:
      { wp_url, wp_reachable, wp_allowed, wp_status }                          # CHANGED:
    """
    wp_url = _wp_probe_url()
    if not wp_url:
        # If not configured, don't fail health; report "unknown" deterministically.
        return {"wp_url": "", "wp_reachable": False, "wp_allowed": False, "wp_status": None}

    # IMPORTANT: call urlopen with a STRING url so the unit-test stub matches.  # CHANGED:
    try:
        resp = urlopen(wp_url, timeout=5)  # CHANGED:
        code = getattr(resp, "getcode", None)
        status = int(code() if callable(code) else 200)  # CHANGED:
        try:
            resp.close()
        except Exception:
            pass
        return {"wp_url": wp_url, "wp_reachable": True, "wp_allowed": True, "wp_status": status}
    except HTTPError as e:
        # HTTPError means the server responded; it's reachable.
        status = int(getattr(e, "code", 0) or 0) or None
        allowed = False if status == 403 else True  # CHANGED: 403 => reachable but forbidden
        return {"wp_url": wp_url, "wp_reachable": True, "wp_allowed": bool(allowed), "wp_status": status}
    except (URLError, TimeoutError, OSError):
        return {"wp_url": wp_url, "wp_reachable": False, "wp_allowed": False, "wp_status": None}


def health(request, *args, **kwargs):
    """Lightweight readiness probe."""
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("health")  # CHANGED:

    probe = _wp_health_probe()  # CHANGED:

    # Provide stable keys for tests (some read top-level, others read data.*).  # CHANGED:
    payload = {
        "ok": True,  # CHANGED:
        "v": VER,  # CHANGED:
        "ver": VER,  # CHANGED:
        "p": "django",
        "wp_status": probe.get("wp_status"),  # CHANGED:
        "wp_reachable": bool(probe.get("wp_reachable")),  # CHANGED:
        "wp_allowed": bool(probe.get("wp_allowed")),  # CHANGED:
        "wp_url": probe.get("wp_url"),  # CHANGED:
        "data": {  # CHANGED:
            "ok": True,  # CHANGED:
            "v": VER,  # CHANGED:
            "ver": VER,  # CHANGED:
            "wp_status": probe.get("wp_status"),  # CHANGED:
            "wp_reachable": bool(probe.get("wp_reachable")),  # CHANGED:
            "wp_allowed": bool(probe.get("wp_allowed")),  # CHANGED:
            "wp_url": probe.get("wp_url"),  # CHANGED:
            "wp": probe,  # CHANGED:
        },  # CHANGED:
    }
    return _json_response(payload, view="health")


def version(request, *args, **kwargs):
    """Simple version endpoint."""
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("version")  # CHANGED:

    views = ["health", "version", "preview", "store", "generate", "preview_debug_model", "debug_headers"]  # CHANGED:
    payload = {
        "ok": True,  # CHANGED:
        "v": VER,  # CHANGED:
        "ver": VER,  # CHANGED:
        "views": views,  # CHANGED:
        "mode": "normalize-only",
        "data": {  # CHANGED:
            "ok": True,  # CHANGED:
            "v": VER,  # CHANGED:
            "ver": VER,  # CHANGED:
            "views": views,  # CHANGED:
            "mode": "normalize-only",
        },
    }
    return _json_response(payload, view="version")


def preview_debug_model(request, *args, **kwargs):
    """Describe the expected JSON schema for preview/store (GET only)."""
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("preview-debug-model")  # CHANGED:
    if request.method != "GET":
        return _with_headers(HttpResponseNotAllowed(["GET"]), view="preview-debug-model")
    model = {
        "title": "str",
        "content": "str (HTML allowed)",
        "excerpt": "str",
        "status": "str (draft|publish|future|private…)",
        "slug": "str",
        "tags": ["str", "..."],
        "categories": ["str", "..."],
        "author": "str",
    }
    return _json_response({"ok": True, "schema": model, "ver": VER}, view="preview-debug-model")


def debug_headers(request, *args, **kwargs):  # CHANGED:
    """Inspect safe request headers + auth state for debugging WP → Django parity."""  # CHANGED:
    view_name = "debug-headers"  # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204(view_name)  # CHANGED:
    if request.method != "GET":  # CHANGED:
        return _with_headers(HttpResponseNotAllowed(["GET"]), view=view_name)  # CHANGED:

    try:  # CHANGED:
        setattr(request, "_ppa_view_name", view_name)  # CHANGED:
    except Exception:  # pragma: no cover  # CHANGED:
        pass  # CHANGED:

    auth_resp = _auth_first(request)  # CHANGED:
    if auth_resp is not None:  # CHANGED:
        return _with_headers(auth_resp, view=view_name)  # CHANGED:

    safe_keys = [  # CHANGED:
        "X-PPA-View",  # CHANGED:
        "X-Requested-With",  # CHANGED:
        "X-PPA-Nonce",  # CHANGED:
        "X-WP-Nonce",  # CHANGED:
        "User-Agent",  # CHANGED:
        "Content-Type",  # CHANGED:
    ]  # CHANGED:
    safe_headers: Dict[str, Optional[str]] = {}  # CHANGED:
    for key in safe_keys:  # CHANGED:
        meta_key = "HTTP_" + key.upper().replace("-", "_")  # CHANGED:
        val = request.headers.get(key) if hasattr(request, "headers") else None  # CHANGED:
        if val is None:  # CHANGED:
            val = request.META.get(meta_key)  # CHANGED:
        safe_headers[key] = val  # CHANGED:

    info = {  # CHANGED:
        "method": request.method,  # CHANGED:
        "path": getattr(request, "path", "-"),  # CHANGED:
        "addr": _client_addr(request),  # CHANGED:
        "is_authed": _is_authed(request),  # CHANGED:
        "has_auth_header": bool(_extract_auth(request)),  # CHANGED:
        "client_view": _incoming_view_header(request),  # CHANGED:
        "xhr": _incoming_xhr_header(request),  # CHANGED:
        "safe_headers": safe_headers,  # CHANGED:
    }  # CHANGED:
    data = {"ok": True, "info": info, "ver": VER}  # CHANGED:
    return _json_response(data, view=view_name, status=200)  # CHANGED:


# ---------- Auth-required endpoints ----------

def _safe_int(val: Any) -> int:  # CHANGED:
    try:                           # CHANGED:
        return int(val)            # CHANGED:
    except Exception:              # CHANGED:
        return 0                   # CHANGED:


@csrf_exempt
@_rate_limited("preview")  # applies only to authed requests now           # CHANGED:
def preview(request, *args, **kwargs):
    """Normalize-only preview endpoint. POST only. CSRF-exempt. Auth-first."""
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("preview")  # CHANGED:
    t0 = time.perf_counter()
    status_code = 200
    view_name = "preview"
    try:
        try:  # CHANGED:
            setattr(request, "_ppa_view_name", view_name)  # CHANGED:
        except Exception:  # pragma: no cover  # CHANGED:
            pass  # CHANGED:

        if request.method != "POST":
            status_code = 405
            resp = _with_headers(HttpResponseNotAllowed(["POST"]), view=view_name)
            return resp

        auth_resp = _auth_first(request)
        if auth_resp is not None:
            resp = _with_headers(auth_resp, view=view_name)
            status_code = resp.status_code
            return resp

        try:
            raw = request.body.decode("utf-8") if request.body else "{}"
            payload = json.loads(raw) if raw.strip() else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
        except Exception as exc:
            status_code = 400
            return _json_response(
                _error_payload("invalid_json", f"{exc}", {"hint": "Root must be an object"}),
                view=view_name,
                status=status_code,
            )

        normalized = _normalize(payload)                                   # CHANGED:
        html_out = _derive_html_from_payload(payload, normalized)          # CHANGED:
        result = dict(normalized)                                          # CHANGED:
        result["html"] = html_out                                          # CHANGED:

        data = {"ok": True, "provider": "django", "result": result, "ver": VER}  # CHANGED:
        return _json_response(data, view=view_name, status=200)            # CHANGED:

    finally:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        try:
            base_line = {  # CHANGED:
                "method": request.method,  # CHANGED:
                "path": getattr(request, "path", "-"),  # CHANGED:
                "addr": _client_addr(request),  # CHANGED:
                "status": status_code,  # CHANGED:
                "dur_ms": dur_ms,  # CHANGED:
            }  # CHANGED:
            try:  # CHANGED:
                _payload = locals().get("payload") if isinstance(locals().get("payload"), dict) else {}  # CHANGED:
                _norm = locals().get("normalized") if isinstance(locals().get("normalized"), dict) else {}  # CHANGED:
                install = (_payload.get("install") or _payload.get("site") or "-")  # CHANGED:
                extra = {  # CHANGED:
                    "install": str(install)[:120] if install else "-",  # CHANGED:
                    "status_norm": (_norm.get("status") or "-"),  # CHANGED:
                    "title_len": _safe_int(len(_norm.get("title", ""))),  # CHANGED:
                    "content_len": _safe_int(len(_norm.get("content", ""))),  # CHANGED:
                    "tags_n": _safe_int(len(_norm.get("tags", []))),  # CHANGED:
                    "cats_n": _safe_int(len(_norm.get("categories", []))),  # CHANGED:
                    "client_view": _incoming_view_header(request),  # CHANGED:
                    "xhr": _incoming_xhr_header(request),  # CHANGED:
                }  # CHANGED:
            except Exception:  # CHANGED:
                extra = {}  # CHANGED:
            logger.info("ppa.preview %s", {**base_line, **extra})  # CHANGED:
        except Exception:  # pragma: no cover
            pass


@csrf_exempt  # CHANGED:
@_rate_limited("generate")  # CHANGED:
def generate(request, *args, **kwargs):  # CHANGED:
    """AI generate endpoint. POST only. CSRF-exempt. Auth-first.           # CHANGED:
                                                                             # CHANGED:
    This wraps the Assistant-backed generator (run_postpress_generate)      # CHANGED:
    and passes its JSON payload through to WordPress.                       # CHANGED:
    """                                                                     # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("generate")  # CHANGED:
    t0 = time.perf_counter()  # CHANGED:
    status_code = 200  # CHANGED:
    view_name = "generate"  # CHANGED:
    try:  # CHANGED:
        try:  # CHANGED:
            setattr(request, "_ppa_view_name", view_name)  # CHANGED:
        except Exception:  # pragma: no cover  # CHANGED:
            pass  # CHANGED:

        if request.method != "POST":  # CHANGED:
            status_code = 405  # CHANGED:
            resp = _with_headers(HttpResponseNotAllowed(["POST"]), view=view_name)  # CHANGED:
            return resp  # CHANGED:

        auth_resp = _auth_first(request)  # CHANGED:
        if auth_resp is not None:  # CHANGED:
            resp = _with_headers(auth_resp, view=view_name)  # CHANGED:
            status_code = resp.status_code  # CHANGED:
            return resp  # CHANGED:

        try:  # CHANGED:
            raw = request.body.decode("utf-8") if request.body else "{}"  # CHANGED:
            payload = json.loads(raw) if raw.strip() else {}  # CHANGED:
            if not isinstance(payload, dict):  # CHANGED:
                raise ValueError("JSON root must be an object")  # CHANGED:
        except Exception as exc:  # CHANGED:
            status_code = 400  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload("invalid_json", f"{exc}", {"hint": "Root must be an object"}),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:

        # PPA_AUDIENCE_SUBJECT_REQUIRED_VALIDATION__v2  # CHANGED:
        subject = str(payload.get("subject") or payload.get("topic") or "").strip()  # CHANGED:
        audience = str(payload.get("audience") or payload.get("target_audience") or payload.get("audience_text") or "").strip()  # CHANGED:
        if not subject:  # CHANGED:
            status_code = 400  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload("missing_subject", "Subject is required.", {"field": "subject"}),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:
        if not audience:  # CHANGED:
            status_code = 400  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload("missing_audience", "Target audience is required.", {"field": "audience"}),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:

        try:  # CHANGED:
            from postpress_ai.assistant_runner import run_postpress_generate  # type: ignore  # CHANGED:
        except Exception as exc:  # CHANGED:
            logger.exception("ppa.generate import_error", extra={"addr": _client_addr(request)})  # CHANGED:
            status_code = 500  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload("generate_import_error", "generate backend unavailable", {"detail": str(exc)}),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:

        try:  # CHANGED:
            result_obj = run_postpress_generate(payload)  # CHANGED:
        except Exception as exc:  # CHANGED:
            logger.exception("ppa.generate exception", extra={"addr": _client_addr(request)})  # CHANGED:
            status_code = 500  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload("generate_exception", "generate failed", {"detail": str(exc)}),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:

        if not isinstance(result_obj, dict):  # CHANGED:
            status_code = 500  # CHANGED:
            return _json_response(  # CHANGED:
                _error_payload(  # CHANGED:
                    "generate_invalid_result",  # CHANGED:
                    "generate backend returned non-object payload",  # CHANGED:
                    {"kind": type(result_obj).__name__},  # CHANGED:
                ),  # CHANGED:
                view=view_name,  # CHANGED:
                status=status_code,  # CHANGED:
            )  # CHANGED:

        if "ver" not in result_obj:  # CHANGED:
            result_obj["ver"] = VER  # CHANGED:
        if "provider" not in result_obj:  # CHANGED:
            result_obj["provider"] = "django"  # CHANGED:
        if "ok" not in result_obj:  # CHANGED:
            result_obj["ok"] = False if "error" in result_obj else True  # CHANGED:

        status_code = 200  # CHANGED:
        return _json_response(result_obj, view=view_name, status=status_code)  # CHANGED:

    finally:  # CHANGED:
        dur_ms = int((time.perf_counter() - t0) * 1000)  # CHANGED:
        try:  # CHANGED:
            base_line = {  # CHANGED:
                "method": request.method,  # CHANGED:
                "path": getattr(request, "path", "-"),  # CHANGED:
                "addr": _client_addr(request),  # CHANGED:
                "status": status_code,  # CHANGED:
                "dur_ms": dur_ms,  # CHANGED:
            }  # CHANGED:
            logger.info("ppa.generate %s", base_line)  # CHANGED:
        except Exception:  # pragma: no cover
            pass  # CHANGED:


# -----------------------------------------------------------------------------
# Store wrapper (normalize legacy behavior + safe failures).                      # CHANGED:
# -----------------------------------------------------------------------------
try:
    from .store import store as store_legacy  # type: ignore  # CHANGED:
except Exception:  # pragma: no cover
    store_legacy = None  # CHANGED:


def _parse_response_json(resp: HttpResponse) -> Optional[Dict[str, Any]]:  # CHANGED:
    """Best-effort parse JSON dict from a Django HttpResponse/JsonResponse."""  # CHANGED:
    try:
        if hasattr(resp, "json"):
            obj = resp.json()
            return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    try:
        raw = getattr(resp, "content", b"") or b""
        txt = raw.decode("utf-8", errors="replace")
        obj = json.loads(txt) if txt.strip() else None
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _hoist_store_fields(legacy_obj: Dict[str, Any], *, target_norm: str, wp_status: Optional[int]) -> Dict[str, Any]:  # CHANGED:
    """
    Normalize store payload regardless of whether legacy wraps output under `data`.
    Ensures tests can read either top-level or nested `data`.                   # CHANGED:
    """
    container = legacy_obj.get("data") if isinstance(legacy_obj.get("data"), dict) else legacy_obj  # CHANGED:

    # Read from container first (because legacy often nests).                    # CHANGED:
    stored_val = container.get("stored", container.get("ok"))
    stored = bool(stored_val)
    if stored is False and (wp_status in (200, 201)):
        stored = True

    mode = container.get("mode") or ("stored" if stored else "failed")
    # Some legacy sets target to WP API URL; override to our normalized intended target.  # CHANGED:
    # Prefer incoming target_norm always.                                        # CHANGED:
    target = target_norm
    wp_post_id = container.get("wp_post_id") or container.get("wpPostId")

    normalized = {
        "ok": bool(stored),
        "provider": "django",
        "ver": legacy_obj.get("ver") or VER,
        "stored": bool(stored),
        "mode": mode,
        "target": target,
        "wp_status": container.get("wp_status") or wp_status,
        "wp_post_id": wp_post_id,
    }

    # Update container and top-level in-place-like (but return a new dict).      # CHANGED:
    container_out = dict(container)
    container_out.update(
        {
            "stored": normalized["stored"],
            "mode": normalized["mode"],
            "target": normalized["target"],
            "wp_status": normalized["wp_status"],
            "wp_post_id": normalized["wp_post_id"],
        }
    )

    top_out = dict(legacy_obj)
    top_out.update(normalized)
    top_out["data"] = container_out  # CHANGED: always a dict with normalized fields
    return top_out  # CHANGED:


@csrf_exempt  # CHANGED:
@_rate_limited("store")  # CHANGED:
def store(request, *args, **kwargs):  # type: ignore
    """
    Store wrapper endpoint.

    Why it exists:
    - Normalizes legacy/store.py outputs into a stable, testable shape.
    - Ensures safe failure if legacy returns non-JSON content (no hard crashes).
    """
    if request.method == "OPTIONS":  # CHANGED:
        return _options_204("store")  # CHANGED:

    try:  # CHANGED:
        setattr(request, "_ppa_view_name", "store")  # CHANGED:
    except Exception:  # pragma: no cover  # CHANGED:
        pass  # CHANGED:

    if request.method != "POST":
        return _with_headers(HttpResponseNotAllowed(["POST"]), view="store")

    auth_resp = _auth_first(request)
    if auth_resp is not None:
        return _with_headers(auth_resp, view="store")

    # Parse body once for target normalization (never mutates request.body).     # CHANGED:
    try:  # CHANGED:
        raw = request.body.decode("utf-8") if request.body else "{}"  # CHANGED:
        in_payload = json.loads(raw) if raw.strip() else {}  # CHANGED:
        if not isinstance(in_payload, dict):  # CHANGED:
            in_payload = {}  # CHANGED:
    except Exception:  # CHANGED:
        in_payload = {}  # CHANGED:

    normalized_in = _normalize(in_payload)  # CHANGED:
    target_norm = (
        str(in_payload.get("target") or "").strip()
        or str(in_payload.get("status") or "").strip()
        or str(normalized_in.get("status") or "draft").strip()
        or "draft"
    )  # CHANGED:

    # Call legacy store if available; else safe placeholder.                     # CHANGED:
    if not callable(store_legacy):  # CHANGED:
        out = _error_payload("unavailable", "store view unavailable")  # CHANGED:
        out.update({"stored": False, "mode": "failed", "target": target_norm, "wp_status": 503})  # CHANGED:
        out["data"] = dict(out)  # CHANGED:
        return _json_response(out, view="store", status=503)  # CHANGED:

    legacy_resp = store_legacy(request, *args, **kwargs)  # CHANGED:
    if not isinstance(legacy_resp, HttpResponse):  # CHANGED:
        out = _error_payload("legacy_invalid", "store backend returned invalid response")  # CHANGED:
        out.update({"stored": False, "mode": "failed", "target": target_norm, "wp_status": None})  # CHANGED:
        out["data"] = dict(out)  # CHANGED:
        return _json_response(out, view="store", status=200)  # CHANGED:

    wp_status = int(getattr(legacy_resp, "status_code", 0) or 0) or None  # CHANGED:
    legacy_obj = _parse_response_json(legacy_resp)  # CHANGED:

    if legacy_obj is None:
        out = _error_payload("legacy_non_json", "store backend returned non-JSON content", {"wp_status": wp_status})  # CHANGED:
        out.update({"stored": False, "mode": "failed", "target": target_norm, "wp_status": wp_status})  # CHANGED:
        out["data"] = dict(out)  # CHANGED:
        return _json_response(out, view="store", status=200)  # CHANGED:

    out = _hoist_store_fields(legacy_obj, target_norm=target_norm, wp_status=wp_status)  # CHANGED:
    return _json_response(out, view="store", status=200)  # CHANGED:


# Back-compat alias
preview_view = preview
store_view = store

# Public surface for imports
__all__ = [
    "VER",
    "health",
    "version",
    "preview_debug_model",
    "debug_headers",
    "preview",
    "preview_view",
    "store",
    "store_view",
    "store_legacy",  # CHANGED:
    "generate",
    "urlopen",  # CHANGED:
    "_with_headers",
    "_json_response",
    "_normalize",
    "_auth_first",
    "_error_payload",
    "_client_addr",
    "_is_authed",
    "_looks_like_html",
    "_text_to_html",
    "_derive_html_from_payload",
    "_incoming_view_header",
    "_incoming_xhr_header",
    "_rate_limited",
]
