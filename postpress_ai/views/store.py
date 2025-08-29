# /home/techwithwayne/agentsuite/postpress_ai/views/store.py
"""
CHANGE LOG
----------
2025-08-16
- FIX (testability & hooks): Resolve STORE_DELEGATE dynamically from the public                 # CHANGED:
  package surface (`postpress_ai.views.STORE_DELEGATE`) at call time instead of                # CHANGED:
  relying on an imported snapshot taken at module import. This ensures tests and               # CHANGED:
  runtime overrides are honored and prevents the resolver from skipping an                     # CHANGED:
  provided delegate in favor of legacy modules.                                                # CHANGED:
- IMPL: Removed the static import of STORE_DELEGATE; `_resolve_store_callable()`                # CHANGED:
  now imports `postpress_ai.views` and reads the attribute each invocation.                    # CHANGED:

2025-08-16
- FIX (failure body propagation): When a legacy delegate returns failure JSON, prefer
  `wp_body`, else fall back to `body`, `message`, or `error` (first found), trimmed to
  600 chars. Previously only `body` was considered, which could drop useful diagnostics.
- KEEP: No contract changes — still normalize to { ok:true, stored:false, id:null,
  mode:"failed", target_used, wp_status, wp_body, ver } on failures.

2025-08-16
- FIX (normalization): Accept string HTTP status codes from legacy dict responses
  (e.g., "201") by coercing to int. Previously, non-int 'status' defaulted to 200,
  which could mask failures or misreport success.
- KEEP: Response envelope and field names are unchanged (no contract changes).

2025-08-16
- NEW FILE: Extracted the /store/ endpoint into a dedicated module.
"""

from __future__ import annotations  # CHANGED:

import json
import logging
from importlib import import_module
from typing import Any, Dict, Optional, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import (  # type: ignore
    _json_response,
    _normalize_header_value,
    _parse_json_body,
    _with_cors,
    _is_url,
    _ppa_key_ok,
    VERSION,
)
# NOTE: do NOT import STORE_DELEGATE here; we resolve it dynamically at call time.             # CHANGED:

log = logging.getLogger("webdoctor")
__all__ = ["store"]


def _resolve_store_callable() -> Callable[[HttpRequest], Any]:  # CHANGED:
    """
    Locate a store delegate. Preference order:
      1) Dynamic hook: postpress_ai.views.STORE_DELEGATE (call-time lookup)
      2) In-package legacy modules under postpress_ai.views (store_post, store_post_legacy)
      3) Top-level legacy modules under postpress_ai (store_post, store_post_legacy)

    Returning the first callable found preserves backward compatibility while enabling
    tests or runtime code to inject STORE_DELEGATE reliably.                                    # CHANGED:
    """
    # 1) Dynamic hook from the public package surface (call-time lookup)                        # CHANGED:
    try:  # CHANGED:
        pkg = import_module("postpress_ai.views")  # CHANGED:
        dynamic_delegate = getattr(pkg, "STORE_DELEGATE", None)  # CHANGED:
        if callable(dynamic_delegate):  # CHANGED:
            log.info("[PPA][store][delegate] used=postpress_ai.views.STORE_DELEGATE")  # CHANGED:
            return dynamic_delegate  # CHANGED:
    except Exception:  # CHANGED:
        pass  # CHANGED:

    # 2) Scan known legacy module names and attributes                                           # CHANGED:
    candidates = ("store_post", "store_post_legacy")
    attr_names = ("store", "handle", "handler", "view", "post", "store_post",
                  "post_store", "delegate", "call", "entry")
    bases = ("postpress_ai.views", "postpress_ai")
    last_import_error = None
    for mod_name in candidates:
        mod = None
        for base in bases:
            full = f"{base}.{mod_name}"
            try:
                mod = import_module(full)
                break
            except Exception as e:
                last_import_error = e
                continue
        if not mod:
            continue
        callable_candidate = getattr(mod, "STORE_CALLABLE", None)
        if callable(callable_candidate):
            log.info("[PPA][store][delegate] used=%s.STORE_CALLABLE", mod.__name__)
            return callable_candidate
        for attr in attr_names:
            fn = getattr(mod, attr, None)
            if callable(fn):
                log.info("[PPA][store][delegate] used=%s.%s", mod.__name__, attr)
                return fn

    # If nothing found, raise to let caller handle as non-json path                             # CHANGED:
    raise AttributeError(f"no-store-callable (last_import_error={type(last_import_error).__name__ if last_import_error else 'None'})")  # CHANGED:


def _coerce_int(val: Any, default: int) -> int:
    """Coerce ints that may arrive as strings (e.g., '201'); fall back to default on error."""
    try:
        if val is None:
            return default
        return int(str(val).strip())
    except Exception:
        return default


def _extract_failure_body(d: Dict[str, Any]) -> str:
    """
    Prefer `wp_body`, else fall back to common fields used by legacy adapters.
    We never log or return huge blobs; trim to 600 characters to keep responses light.
    """
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

    # Normalize body: permit 'content' as a synonym for 'html' to support old clients.
    body = _parse_json_body(request)
    if "html" not in body and "content" in body and isinstance(body.get("content"), str):
        body["html"] = body["content"]

    requested_target = (body.get("target") or "draft").strip() or "draft"

    # Auth check (with test bypass); never log secrets — only lengths and match flag.
    if not _ppa_key_ok(request):
        return _json_response(
            {"ok": True, "stored": False, "id": None, "mode": "failed",
             "target_used": requested_target, "wp_status": "forbidden", "wp_body": "forbidden"},
            200, request
        )

    # Delegate to any legacy/store implementation; guard with a broad try to prevent crashes.
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

    # ----- Helpers to finalize normalized envelopes -----
    def _finalize_success(env: Dict[str, Any]) -> JsonResponse:
        env["ok"] = True; env["stored"] = True; env["mode"] = "created"
        env["target_used"] = env.get("target_used", requested_target)
        return _json_response(env, 200, request)

    def _finalize_failure(env: Dict[str, Any]) -> JsonResponse:
        env["ok"] = True; env["stored"] = False; env["mode"] = "failed"; env["id"] = None
        env["target_used"] = env.get("target_used", requested_target)
        if "wp_body" not in env: env["wp_body"] = "unknown"
        return _json_response(env, 200, request)

    # ----- Case A: Delegate returned a Django HttpResponse -----
    if isinstance(legacy_resp, HttpResponse):
        status_code = int(getattr(legacy_resp, "status_code", 200))
        raw_body = legacy_resp.content.decode("utf-8", errors="replace")
        parsed: Optional[Dict[str, Any]] = None
        try:
            parsed = json.loads(raw_body)
        except Exception:
            parsed = None

        if 200 <= status_code < 300:
            # Success: infer stored:true even if JSON is minimal or missing.
            env: Dict[str, Any] = {"id": (parsed.get("id") if isinstance(parsed, dict) else None)}
            legacy_target = (parsed.get("target") if isinstance(parsed, dict) else None)
            if not legacy_target or _is_url(str(legacy_target)):
                env["target_used"] = requested_target
            else:
                env["target_used"] = str(legacy_target)
            env["wp_status"] = (parsed.get("wp_status") if isinstance(parsed, dict) else None) or status_code
            return _finalize_success(env)

        # Failure: try to propagate a meaningful body; otherwise normalized non-JSON.
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

    # ----- Case B: Delegate returned a plain dict (legacy JSON object) -----
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

    # ----- Case C: Unknown/empty delegate result → normalized failure -----
    return _finalize_failure({"wp_status": "delegate-empty"})
