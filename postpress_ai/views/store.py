"""
/store/ endpoint
"""

from __future__ import annotations

import json
import logging
from importlib import import_module
from typing import Any, Dict, Optional, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .utils import (
    _json_response, _normalize_header_value, _parse_json_body, 
    _with_cors, _is_url, _ppa_key_ok, VERSION
)

log = logging.getLogger("webdoctor")
__all__ = ["store"]

def _resolve_store_callable() -> Callable[[HttpRequest], Any]:
    """Locate a store delegate."""
    # 1) Dynamic hook from the public package surface
    try:
        pkg = import_module("postpress_ai.views")
        dynamic_delegate = getattr(pkg, "STORE_DELEGATE", None)
        if callable(dynamic_delegate):
            log.info("[PPA][store][delegate] used=postpress_ai.views.STORE_DELEGATE")
            return dynamic_delegate
    except Exception:
        pass

    # 2) Scan known legacy module names
    candidates = ("store_post", "store_post_legacy")
    attr_names = ("store", "handle", "handler", "view", "post", "store_post",
                  "post_store", "delegate", "call", "entry")
    bases = ("postpress_ai.views", "postpress_ai")
    
    for mod_name in candidates:
        mod = None
        for base in bases:
            full = f"{base}.{mod_name}"
            try:
                mod = import_module(full)
                break
            except Exception:
                continue
        if not mod:
            continue
        
        for attr in attr_names:
            fn = getattr(mod, attr, None)
            if callable(fn):
                log.info("[PPA][store][delegate] used=%s.%s", mod.__name__, attr)
                return fn

    raise AttributeError("no-store-callable")

def _coerce_int(val: Any, default: int) -> int:
    """Coerce ints that may arrive as strings."""
    try:
        if val is None:
            return default
        return int(str(val).strip())
    except Exception:
        return default

def _extract_failure_body(d: Dict[str, Any]) -> str:
    """Prefer `wp_body`, else fall back to common fields."""
    for key in ("wp_body", "body", "message", "error"):
        v = d.get(key)
        if isinstance(v, str) and v:
            return v[:600]
    return "unknown"

@csrf_exempt
def store(request: HttpRequest) -> JsonResponse:
    log.info("[PPA][store][entry] host=%s origin=%s",
             _normalize_header_value(request.META.get("HTTP_HOST")),
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    
    if request.method == "OPTIONS":
        return _with_cors(HttpResponse(status=204), request)
    if request.method != "POST":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    body = _parse_json_body(request)
    if "html" not in body and "content" in body and isinstance(body.get("content"), str):
        body["html"] = body["content"]

    requested_target = (body.get("target") or "draft").strip() or "draft"

    if not _ppa_key_ok(request):
        return _json_response(
            {"ok": True, "stored": False, "id": None, "mode": "failed",
             "target_used": requested_target, "wp_status": "forbidden", "wp_body": "forbidden"},
            200, request
        )

    # Delegate to any legacy/store implementation
    try:
        delegate_fn = _resolve_store_callable()
        legacy_resp: Any = delegate_fn(request)
    except Exception as e:
        log.info("[PPA][store][delegate] exception=%s → treating as non-json", e.__class__.__name__)
        return _json_response(
            {"ok": True, "stored": False, "id": None, "mode": "failed",
             "target_used": requested_target, "wp_status": "non-json", "wp_body": "delegate-exception"},
            200, request
        )

    # Normalize response
    def _finalize_success(env: Dict[str, Any]) -> JsonResponse:
        env["ok"] = True; env["stored"] = True; env["mode"] = "created"
        env["target_used"] = env.get("target_used", requested_target)
        return _json_response(env, 200, request)

    def _finalize_failure(env: Dict[str, Any]) -> JsonResponse:
        env["ok"] = True; env["stored"] = False; env["mode"] = "failed"; env["id"] = None
        env["target_used"] = env.get("target_used", requested_target)
        if "wp_body" not in env: env["wp_body"] = "unknown"
        return _json_response(env, 200, request)

    # Handle HttpResponse
    if isinstance(legacy_resp, HttpResponse):
        status_code = int(getattr(legacy_resp, "status_code", 200))
        raw_body = legacy_resp.content.decode("utf-8", errors="replace")
        parsed: Optional[Dict[str, Any]] = None
        try:
            parsed = json.loads(raw_body)
        except Exception:
            parsed = None

        if 200 <= status_code < 300:
            env: Dict[str, Any] = {"id": (parsed.get("id") if isinstance(parsed, dict) else None)}
            legacy_target = (parsed.get("target") if isinstance(parsed, dict) else None)
            if not legacy_target or _is_url(str(legacy_target)):
                env["target_used"] = requested_target
            else:
                env["target_used"] = str(legacy_target)
            env["wp_status"] = (parsed.get("wp_status") if isinstance(parsed, dict) else None) or status_code
            return _finalize_success(env)

        if isinstance(parsed, dict):
            env = {"id": parsed.get("id")}
            legacy_target = parsed.get("target")
            if not legacy_target or _is_url(str(legacy_target)):
                env["target_used"] = requested_target
            else:
                env["target_used"] = str(legacy_target)
            env["wp_status"] = parsed.get("wp_status", status_code)
            env["wp_body"] = _extract_failure_body(parsed)
            return _finalize_failure(env)

        return _finalize_failure({"wp_status": "non-json", "wp_body": raw_body[:600], "target_used": requested_target})

    # Handle dict response
    if isinstance(legacy_resp, dict):
        parsed = legacy_resp
        status_code = _coerce_int(parsed.get("status"), 200)

        env: Dict[str, Any] = {"id": parsed.get("id")}
        legacy_target = parsed.get("target")
        if not legacy_target or _is_url(str(legacy_target)):
            env["target_used"] = requested_target
        else:
            env["target_used"] = str(legacy_target)

        if 200 <= status_code < 300:
            env["wp_status"] = parsed.get("wp_status", status_code)
            return _finalize_success(env)
        else:
            env["wp_status"] = parsed.get("wp_status", status_code)
            env["wp_body"] = _extract_failure_body(parsed)
            return _finalize_failure(env)

    return _finalize_failure({"wp_status": "delegate-empty"})
