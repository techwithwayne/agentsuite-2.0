"""
PostPress AI — views package

CHANGE LOG
----------
2025-10-26 • Implement normalize-only preview view with auth-first, CSRF-exempt.               # CHANGED:
2025-10-26 • Package-level exports: preview, store (import from .store).                      # CHANGED:
2025-10-26 • Add Cache-Control and X-PPA-View headers, ver="1".                               # CHANGED:
2025-10-26 • Ensure headers on ALL responses (405/auth), add _with_headers helper.            # CHANGED:
2025-10-26 • Surface VER and helpers (_with_headers, _json_response, _normalize) via __all__. # CHANGED:
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from django.http import JsonResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Attempt to import the already-implemented store view (normalize-only).
# Falls back to a 503 placeholder if not present, but attribute will exist for imports.
try:
    from .store import store  # type: ignore
except Exception:  # pragma: no cover
    def store(request, *args, **kwargs):  # noqa: D401
        """Temporary placeholder when store view is unavailable."""
        resp = JsonResponse(
            {"ok": False, "error": "store view unavailable", "ver": "1"},
            status=503,
        )
        resp["X-PPA-View"] = "normalize"
        resp["Cache-Control"] = "no-store"
        return resp

VER = "1"


def _get_shared_key() -> str:
    # Read raw, then strip quotes/whitespace
    raw = os.environ.get("PPA_SHARED_KEY", "")
    return raw.strip().strip('"').strip("'").strip()


def _extract_auth(request) -> str:
    """
    Return the presented key (if any) from either X-PPA-Key or Authorization: Bearer <key>.
    """
    key = request.headers.get("X-PPA-Key") or request.META.get("HTTP_X_PPA_KEY")
    if key:
        return key.strip().strip('"').strip("'").strip()

    auth = request.headers.get("Authorization") or request.META.get("HTTP_AUTHORIZATION")
    if not auth:
        return ""
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip().strip('"').strip("'").strip()
    return ""


def _auth_first(request) -> HttpResponse | None:
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
    """
    Normalize incoming payload into the response schema. Django never writes to WP.
    """
    def _list(val: Any) -> List[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(x) for x in val]
        return [str(val)]

    result = {
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
    return result


def _with_headers(resp: HttpResponse, *, view: str) -> HttpResponse:
    """
    Apply required minimal breadcrumb + no-store headers to any response object.
    """
    resp["X-PPA-View"] = view
    resp["Cache-Control"] = "no-store"
    return resp


def _json_response(data: Dict[str, Any], *, view: str, status: int = 200) -> JsonResponse:
    resp = JsonResponse(data, status=status)
    return _with_headers(resp, view=view)


@csrf_exempt
def preview(request, *args, **kwargs):  # noqa: D401
    """Normalize-only preview endpoint. POST only. CSRF-exempt. Auth-first."""
    # Enforce method (ensure headers even for 405)
    if request.method != "POST":
        return _with_headers(HttpResponseNotAllowed(["POST"]), view="preview")

    # Auth-first (even if JSON is bad)
    auth_resp = _auth_first(request)
    if auth_resp is not None:
        return _with_headers(auth_resp, view="preview")

    # Parse JSON body safely
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


# Back-compat alias (explicit surface)
preview_view = preview  # alias for clarity

# Public surface for imports
__all__ = [
    "VER",
    # views
    "preview", "preview_view", "store",
    # helpers
    "_with_headers", "_json_response", "_normalize",
]
