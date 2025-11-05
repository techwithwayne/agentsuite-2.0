"""
PostPress AI — views package

CHANGE LOG
----------
2025-11-05 • Rate limit counts ONLY authenticated hits; add _is_authed helper; keep structured 429 + headers.   # CHANGED:
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


def _is_authed(request) -> bool:  # CHANGED:
    """Fast boolean check for auth success without constructing a response."""  # CHANGED:
    presented = _extract_auth(request)  # CHANGED:
    expected = _get_shared_key()        # CHANGED:
    return bool(presented) and bool(expected) and (presented == expected)  # CHANGED:


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

    - No key presented  -> 401
    - Wrong key         -> 403
    """
    presented = _extract_auth(request)
    expected = _get_shared_key()

    if not presented:
        return JsonResponse(_error_payload("missing_key", "missing authentication key"), status=401)
    if not expected or presented != expected:
        return JsonResponse(_error_payload("forbidden", "invalid authentication key"), status=403)
    return None


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
    **Now counts only authenticated requests**; unauthenticated requests bypass the bucket
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
        "views": ["health", "version", "preview", "store", "preview_debug_model"],
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


# ---------- Auth-required endpoints ----------

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

        normalized = _normalize(payload)
        data = {"ok": True, "result": normalized, "ver": VER}
        return _json_response(data, view=view_name, status=200)

    finally:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        try:
            logger.info(
                "ppa.preview %s %s addr=%s status=%s dur_ms=%s",
                request.method,
                getattr(request, "path", "-"),
                _client_addr(request),
                status_code,
                dur_ms,
            )
        except Exception:  # pragma: no cover
            pass


# -----------------------------------------------------------------------------
# Import store AFTER helpers are defined to avoid circular import.
# -----------------------------------------------------------------------------
try:
    from .store import store  # type: ignore
except Exception:  # pragma: no cover
    def store(request, *args, **kwargs):  # type: ignore
        # Structured placeholder if store.py fails to import
        data = _error_payload("unavailable", "store view unavailable")
        resp = JsonResponse(data, status=503)
        resp = _with_headers(resp, view="normalize")
        return resp


# Back-compat alias
preview_view = preview
store_view = store

# Public surface for imports
__all__ = [
    "VER",
    # views
    "health", "version", "preview_debug_model",
    "preview", "preview_view", "store", "store_view",
    # helpers
    "_with_headers", "_json_response", "_normalize",
    "_auth_first", "_error_payload", "_client_addr", "_is_authed",  # CHANGED:
    # rate limit
    "_rate_limited",
]
