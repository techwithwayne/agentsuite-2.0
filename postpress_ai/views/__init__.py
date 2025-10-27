"""
PostPress AI — views package

CHANGE LOG
----------
2025-10-27 • Add public health/version + preview_debug_model; preview normalize-only; robust headers; safe store import.  # CHANGED:
2025-10-26 • Normalize-only preview; auth-first; CSRF-exempt.                                                                # CHANGED:
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Attempt to import the already-implemented store view.
# If unavailable, we provide a placeholder that returns 503 but keeps imports working.
try:
    from .store import store  # type: ignore
except Exception:  # pragma: no cover
    def store(request, *args, **kwargs):  # type: ignore
        resp = JsonResponse(
            {"ok": False, "error": "store view unavailable", "ver": "1"},
            status=503,
        )
        resp["X-PPA-View"] = "normalize"
        resp["Cache-Control"] = "no-store"
        return resp

VER = "1"


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


def _auth_first(request) -> Optional[HttpResponse]:
    """
    Enforce auth before any other processing.

    - No key presented  -> 401
    - Wrong key         -> 403
    """
    presented = _extract_auth(request)
    expected = _get_shared_key()

    if not presented:
        return JsonResponse({"ok": False, "error": "missing key", "ver": VER}, status=401)
    if not expected or presented != expected:
        return JsonResponse({"ok": False, "error": "forbidden", "ver": VER}, status=403)
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
def preview(request, *args, **kwargs):
    """Normalize-only preview endpoint. POST only. CSRF-exempt. Auth-first."""
    if request.method != "POST":
        return _with_headers(HttpResponseNotAllowed(["POST"]), view="preview")

    auth_resp = _auth_first(request)
    if auth_resp is not None:
        return _with_headers(auth_resp, view="preview")

    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("JSON root must be an object")
    except Exception as exc:
        return _json_response(
            {"ok": False, "error": f"invalid json: {exc}", "ver": VER},
            view="preview",
            status=400,
        )

    normalized = _normalize(payload)
    return _json_response({"ok": True, "result": normalized, "ver": VER}, view="preview")


# Back-compat alias
preview_view = preview

# Public surface for imports
__all__ = [
    "VER",
    # views
    "health", "version", "preview_debug_model",
    "preview", "preview_view", "store",
    # helpers
    "_with_headers", "_json_response", "_normalize",
]
