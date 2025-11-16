"""
PostPress AI — views.store

CHANGE LOG
----------
2025-11-16 • Preserve optional 'mode' hint in result + telemetry.                 # CHANGED:
2025-11-13 • Add client_view/xhr logging parity with preview; no behavior changes.        # CHANGED:
2025-11-11 • Doc/clarity pass; confirm parity & headers; no behavior change.             # (prev)
2025-11-10 • Add structured, safe logging parity: install/wp_post_id/status/lengths...   # (prev)
2025-11-10 • Parity with WP controller response shape...                                 # (prev)
2025-11-05 • Add rate-limit...                                                           # (prev)
2025-10-27 • Exception guard...                                                          # (prev)
2025-10-26 • Normalize-only store view...                                                # (prev)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

# Shared helpers (import AFTER json)
from . import (  # type: ignore
    _auth_first,
    _json_response,
    _normalize,
    _with_headers,
    _client_addr,
    _error_payload,
    _incoming_view_header,      # CHANGED:
    _incoming_xhr_header,       # CHANGED:
    _rate_limited,
    VER,
)

logger = logging.getLogger(__name__)


def _extract_injected_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract optional meta values that WP can inject into the payload.

    The WP controller may send some meta alongside the core content fields so they
    can be mirrored back at the top-level of the response for convenience and so
    structured logging can capture them.
    """
    meta: Dict[str, Any] = {}

    install = payload.get("install") or payload.get("site")
    if isinstance(install, str) and install.strip():
        meta["install"] = install.strip()

    wp_post_id = payload.get("id") or payload.get("wp_post_id")
    if isinstance(wp_post_id, (str, int)):
        meta["id"] = wp_post_id

    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        meta["status"] = status.strip()

    permalink = payload.get("permalink")
    if isinstance(permalink, str) and permalink.strip():
        meta["permalink"] = permalink.strip()

    edit_link = payload.get("edit_link")
    if isinstance(edit_link, str) and edit_link.strip():
        meta["edit_link"] = edit_link.strip()
    return meta


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
        if request.method != "POST":
            status_code = 405
            return _with_headers(HttpResponseNotAllowed(["POST"]), view=view_name)

        auth_resp: Optional[JsonResponse] = _auth_first(request)
        if auth_resp is not None:
            status_code = auth_resp.status_code
            return _with_headers(auth_resp, view=view_name)

        try:
            raw = request.body.decode("utf-8") if request.body else "{}"
            payload: Dict[str, Any] = json.loads(raw) if raw.strip() else {}
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
        # Ensure optional 'mode' hint is preserved in the normalized result.      # CHANGED:
        try:                                                                     # CHANGED:
            if isinstance(payload, dict) and isinstance(normalized, dict):      # CHANGED:
                mode_val = payload.get("mode")                                   # CHANGED:
                if isinstance(mode_val, str) and mode_val.strip():              # CHANGED:
                    normalized["mode"] = mode_val.strip().lower()               # CHANGED:
        except Exception:                                                        # CHANGED:
            # Logging will still include a safe placeholder if this fails.      # CHANGED:
            pass                                                                # CHANGED:
        injected_meta = _extract_injected_meta(payload)

        result: Dict[str, Any] = {"ok": True, "result": normalized, "ver": VER}
        if injected_meta:
            result["result"] = {**normalized, "meta": injected_meta}
            for k, v in injected_meta.items():
                result[k] = v

        return _json_response(result, view=view_name, status=200)

    except Exception as exc:
        detail = (str(exc) or exc.__class__.__name__)[:200]
        status_code = 500
        return _json_response(
            _error_payload("server_error", "unexpected server error", {"detail": detail}),
            view=view_name,
            status=status_code,
        )

    finally:
        dur_ms = int((time.perf_counter() - t0) * 1000)
        try:
            base_line = {
                "method": request.method,
                "path": getattr(request, "path", "-"),
                "addr": _client_addr(request),
                "status": status_code,
                "dur_ms": dur_ms,
            }
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

                    # Simple mode hint for telemetry (draft/publish/update).       # CHANGED:
                    "mode": (                                                          # CHANGED:
                        (normalized.get("mode") if isinstance(normalized, dict) else None)  # CHANGED:
                        or (payload.get("mode") if isinstance(payload, dict) else None)      # CHANGED:
                        or "-"                                                          # CHANGED:
                    ),                                                          # CHANGED:

                    # ------------------------
                    # NEW parity fields        # CHANGED:
                    # ------------------------
                    "client_view": _incoming_view_header(request),     # CHANGED:
                    "xhr": _incoming_xhr_header(request),              # CHANGED:
                }
            except Exception:
                extra = {}

            logger.info("ppa.store %s", {**base_line, **extra})  # CHANGED:
        except Exception:
            pass


store_view = store

__all__ = ["store", "store_view"]
