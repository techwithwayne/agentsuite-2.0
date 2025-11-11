"""
PostPress AI — views.store

CHANGE LOG
----------
2025-11-11 • Doc/clarity pass; confirm parity & headers; no behavior change.                                    # CHANGED:
2025-11-10 • Add structured, safe logging parity: install/wp_post_id/status/lengths/tags_n/cats_n; keep headers + shape.  # CHANGED:
2025-11-10 • Parity with WP controller response shape: surface optional {id, permalink, edit_link} top-level and in result.meta; set X-PPA-View=store.
2025-11-05 • Add light rate-limit/debounce (5 req/10s per client) with structured 429; keep X-PPA-View=normalize.
2025-11-05 • Structured error shape + safe request logging; ver=pa.v1; keep X-PPA-View: normalize.
2025-10-27 • Add robust exception guard to return JSON 500 with headers (no PA HTML page).
2025-10-26 • Normalize-only store view, auth-first, CSRF-exempt.
2025-10-26 • Shared helpers from package (__init__) for consistency.
2025-10-26 • Ensure headers on ALL responses (405/auth) via _with_headers helper.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Import shared helpers and version from package to keep a single source of truth.
from . import (  # type: ignore
    _auth_first,
    _json_response,
    _normalize,
    _with_headers,
    VER,
    _error_payload,
    _rate_limited,
)

# Local logger (safe, no secrets).
logger = logging.getLogger("postpress_ai.views")


def _client_addr(request) -> str:
    """Best-effort client address for logs (no secrets)."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "-"


def _extract_injected_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pull optional WP-provided identifiers/links so Django's /store/ mirrors WP controller shape.
    We DO NOT construct these; we only surface what was provided.
    """
    # CHANGED: begin meta extraction
    pid = payload.get("id") or payload.get("wp_post_id") or payload.get("post_id")  # CHANGED:
    permalink = payload.get("permalink") or payload.get("link") or payload.get("url")
    edit_link = payload.get("edit_link") or payload.get("edit")

    meta: Dict[str, Any] = {}
    if pid is not None:
        meta["id"] = pid
    if isinstance(permalink, str) and permalink.strip():
        meta["permalink"] = permalink.strip()
    if isinstance(edit_link, str) and edit_link.strip():
        meta["edit_link"] = edit_link.strip()
    return meta
    # CHANGED: end meta extraction


def _safe_int(val: Any) -> int:
    try:
        return int(val)
    except Exception:
        return 0


@csrf_exempt
@_rate_limited("store")
def store(request, *args, **kwargs):  # noqa: D401
    """Normalize-only store endpoint. POST only. CSRF-exempt. Auth-first."""
    t0 = time.perf_counter()
    status_code = 200
    view_name = "store"
    try:
        # Enforce method (ensure headers even for 405)
        if request.method != "POST":
            status_code = 405  # CHANGED:
            return _with_headers(HttpResponseNotAllowed(["POST"]), view=view_name)

        # Auth-first (even if JSON is malformed)
        auth_resp: Optional[JsonResponse] = _auth_first(request)
        if auth_resp is not None:
            status_code = auth_resp.status_code
            return _with_headers(auth_resp, view=view_name)

        # Parse JSON body safely
        try:
            raw = request.body.decode("utf-8") if request.body else "{}"
            payload: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
        except Exception as exc:
            status_code = 400  # CHANGED:
            return _json_response(
                _error_payload("invalid_json", f"{exc}", {"hint": "Root must be an object"}),  # CHANGED:
                view=view_name,
                status=status_code,
            )

        # Normalize core fields (no WP writes here; this is still "normalize-only")
        normalized = _normalize(payload)

        # CHANGED: If WP passed back identifiers/links (after creating a local draft),
        # surface them top-level AND under result.meta for parity and convenience.
        injected_meta = _extract_injected_meta(payload)  # CHANGED:
        result: Dict[str, Any] = {"ok": True, "result": normalized, "ver": VER}  # CHANGED:
        if injected_meta:  # CHANGED:
            # Attach under result.meta
            result["result"] = {**normalized, "meta": injected_meta}  # CHANGED:
            # Also mirror at top-level for simpler client access (parity with WP)  # CHANGED:
            for k, v in injected_meta.items():
                result[k] = v  # CHANGED:

        return _json_response(result, view=view_name, status=200)  # CHANGED:

    except Exception as exc:  # final guard to avoid PA HTML error page
        # Trim the exception text to something compact; avoid leaking internals
        detail = (str(exc) or exc.__class__.__name__)[:200]
        status_code = 500  # CHANGED:
        return _json_response(
            _error_payload("server_error", "unexpected server error", {"detail": detail}),  # CHANGED:
            view=view_name,
            status=status_code,
        )

    finally:
        # Safe access log with timing (ms) + structured fields (no secrets).        # CHANGED:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        try:
            # Basic request facts
            base_line = {
                "method": request.method,
                "path": getattr(request, "path", "-"),
                "addr": _client_addr(request),
                "status": status_code,
                "dur_ms": dur_ms,
            }
            # Structured fields from payload/normalized (wrapped in try so logging never breaks)
            try:
                install = (payload.get("install") or payload.get("site") or "-") if isinstance(payload, dict) else "-"
                meta = injected_meta if isinstance(locals().get("injected_meta"), dict) else {}
                wp_post_id = meta.get("id", payload.get("id") if isinstance(payload, dict) else None)

                extra = {
                    "install": str(install)[:120] if install else "-",
                    "wp_post_id": wp_post_id if isinstance(wp_post_id, (str, int)) else None,
                    "status_norm": (normalized.get("status") if isinstance(normalized, dict) else None) or "-",
                    "title_len": _safe_int(len(normalized.get("title", ""))) if isinstance(normalized, dict) else 0,
                    "content_len": _safe_int(len(normalized.get("content", ""))) if isinstance(normalized, dict) else 0,
                    "tags_n": _safe_int(len(normalized.get("tags", []) if isinstance(normalized, dict) else [])),
                    "cats_n": _safe_int(len(normalized.get("categories", []) if isinstance(normalized, dict) else [])),
                }
            except Exception:
                extra = {}

            # Emit single structured line (compact; no secrets/content)
            logger.info("ppa.store %s", {**base_line, **extra})  # CHANGED:
        except Exception:  # pragma: no cover
            pass


# Back-compat alias
store_view = store

__all__ = ["store", "store_view"]
