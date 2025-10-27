"""
PostPress AI — views.store

CHANGE LOG
----------
2025-10-26 • Normalize-only store view, auth-first, CSRF-exempt.
2025-10-26 • Shared helpers from package (__init__) for consistency.
2025-10-26 • Ensure headers on ALL responses (405/auth) via _with_headers helper.
2025-10-27 • Add robust exception guard to return JSON 500 with headers (no PA HTML page).
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
    try:
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

    except Exception as exc:  # final guard to avoid PA HTML error page
        # Trim the exception text to something compact; avoid leaking internals
        detail = (str(exc) or exc.__class__.__name__)[:200]
        return _json_response(
            {"ok": False, "error": "server", "detail": detail, "ver": VER},
            view="normalize",
            status=500,
        )


# Back-compat alias
store_view = store

__all__ = ["store", "store_view"]
