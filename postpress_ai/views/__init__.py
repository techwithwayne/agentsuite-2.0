"""
PostPress AI — views package

CHANGE LOG
----------
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

from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Logger (safe, no secrets logged).
logger = logging.getLogger("postpress_ai.views")

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


# ---------- Public endpoints (no auth) ----------

def health(request, *args, **kwargs):
    """Lightweight readiness probe."""
    return _json_response({"ok": True, "v": VER, "p": "django"}, view="health")


def version(request, *args, **kwargs):
    """Simple version endpoint."""
    payload = {
        "ok": True,
        "v": VER,
        "views": ["health", "version", "preview", "store", "generate", "preview_debug_model", "debug_headers"],  # CHANGED:
        "mode": "normalize-only",
    }
    return _json_response(payload, view="version")


def preview_debug_model(request, *args, **kwargs):
    """Describe the expected JSON schema for preview/store (GET only)."""
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
    if request.method != "GET":  # CHANGED:
        return _with_headers(HttpResponseNotAllowed(["GET"]), view=view_name)  # CHANGED:

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
    t0 = time.perf_counter()
    status_code = 200
    view_name = "preview"
    try:
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
            # CHANGED: structured, safe logging parity with store()
            base_line = {  # CHANGED:
                "method": request.method,  # CHANGED:
                "path": getattr(request, "path", "-"),  # CHANGED:
                "addr": _client_addr(request),  # CHANGED:
                "status": status_code,  # CHANGED:
                "dur_ms": dur_ms,  # CHANGED:
            }  # CHANGED:
            try:  # CHANGED:
                # Safely access locals if early exit occurred                  # CHANGED:
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
    t0 = time.perf_counter()  # CHANGED:
    status_code = 200  # CHANGED:
    view_name = "generate"  # CHANGED:
    try:  # CHANGED:
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

        # Import the Assistant runner lazily to avoid any circular import surprises.  # CHANGED:
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

        # Normalize minimal contract fields without disturbing the backend shape.     # CHANGED:
        if "ver" not in result_obj:  # CHANGED:
            result_obj["ver"] = VER  # CHANGED:
        if "provider" not in result_obj:  # CHANGED:
            result_obj["provider"] = "django"  # CHANGED:
        if "ok" not in result_obj:  # CHANGED:
            # If there's an explicit error, default ok=False; otherwise assume success.  # CHANGED:
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
            try:  # CHANGED:
                _payload = locals().get("payload") if isinstance(locals().get("payload"), dict) else {}  # CHANGED:
                install = (_payload.get("install") or _payload.get("site") or "-")  # CHANGED:
                extra = {  # CHANGED:
                    "install": str(install)[:120] if install else "-",  # CHANGED:
                    "client_view": _incoming_view_header(request),  # CHANGED:
                    "xhr": _incoming_xhr_header(request),  # CHANGED:
                }  # CHANGED:
            except Exception:  # CHANGED:
                extra = {}  # CHANGED:
            logger.info("ppa.generate %s", {**base_line, **extra})  # CHANGED:
        except Exception:  # pragma: no cover
            pass  # CHANGED:


# -----------------------------------------------------------------------------
# Import store AFTER helpers are defined to avoid circular import.
# -----------------------------------------------------------------------------
try:
    from .store import store  # type: ignore
except Exception:  # pragma: no cover
    @csrf_exempt  # CHANGED:
    @_rate_limited("store")  # CHANGED:
    def store(request, *args, **kwargs):  # type: ignore
        """Structured placeholder if store view unavailable."""  # CHANGED:
        data = _error_payload("unavailable", "store view unavailable")
        resp = JsonResponse(data, status=503)
        resp = _with_headers(resp, view="store")  # CHANGED:
        return resp  # CHANGED:


# Back-compat alias
preview_view = preview
store_view = store

# Public surface for imports
__all__ = [
    "VER",
    # views
    "health",
    "version",
    "preview_debug_model",
    "debug_headers",
    "preview",
    "preview_view",
    "store",
    "store_view",
    "generate",  # CHANGED:
    # helpers
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
    # rate limit
    "_rate_limited",
]
