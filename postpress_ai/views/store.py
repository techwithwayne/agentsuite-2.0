"""
PostPress AI — views.store

CHANGE LOG
----------
2025-10-26 • Implement normalize-only store view, auth-first, CSRF-exempt.                # CHANGED:
2025-10-26 • Uses shared helpers from package (__init__) for consistency.                  # CHANGED:
2025-10-26 • Adds Cache-Control and X-PPA-View headers, ver="1".                           # CHANGED:
2025-10-26 • Ensure headers on ALL responses (405/auth) via _with_headers helper.          # CHANGED:
"""

from __future__ import annotations

import json
from typing import Any, Dict

from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Import shared helpers and version from package to keep a single source of truth.
from . import _auth_first, _json_response, _normalize, _with_headers, VER  # type: ignore


@csrf_exempt
def store(request, *args, **kwargs):  # noqa: D401
    """Normalize-only store endpoint. POST only. CSRF-exempt. Auth-first."""
    # Enforce method (ensure headers even for 405)
    if request.method != "POST":
        return _with_headers(HttpResponseNotAllowed(["POST"]), view="normalize")

    # Auth-first (even if JSON is malformed)
    auth_resp = _auth_first(request)
    if auth_resp is not None:
        return _with_headers(auth_resp, view="normalize")

    # Parse JSON body safely
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        payload: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("JSON root must be an object")
    except Exception as exc:
        return _json_response(
            {"ok": False, "error": f"invalid json: {exc}", "ver": VER},
            view="normalize",
            status=400,
        )

    normalized = _normalize(payload)
    return _json_response({"ok": True, "result": normalized, "ver": VER}, view="normalize")


# Back-compat alias
store_view = store

__all__ = ["store", "store_view"]
