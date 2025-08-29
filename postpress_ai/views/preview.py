# /home/techwithwayne/agentsuite/postpress_ai/views/preview.py
"""
CHANGE LOG
----------
2025-08-22
- HARDENING: Wrap delegate call `_pp.preview(request)` in try/except so any provider
  exception returns a deterministic local **success** payload instead of a 500 HTML page.  # CHANGED:
  Bumps telemetry (delegate_bad + fallback_local) and preserves CORS/contract.             # CHANGED:

2025-08-17
- CONSISTENCY: Return **204** for CORS preflight (OPTIONS) like other endpoints.                # CHANGED:
  Previously returned 200 JSON; behavior is now aligned with /health and tests.               # CHANGED:

2025-08-17
- FEATURE: Add env flag `PPA_PREVIEW_FORCE_FALLBACK` to force local preview (for drills/ops).
  Accepts truthy values: "1", "true", "yes", "force" (case-insensitive).
  Enforces auth + returns the deterministic local success payload.
  Injects provider marker `<!-- provider: forced -->` for clear diagnostics.
- HARDENING: Handle CORS preflight (OPTIONS) *before* delegate dispatch so preflight always works.
- TELEMETRY: Add `forced_fallback` counter to distinguish operator-forced drills from outages.

2025-08-16
- FIX (auth consistency): Enforce X-PPA-Key on the LOCAL FALLBACK path so POST /preview/
  always requires auth, matching the spec. OPTIONS preflight remains open.
- ENHANCEMENT (delegate hardening): When delegating to `preview_post.preview`, ensure
  the JSON response always includes `ver` and reflect allowed CORS on the delegate
  response without altering any other headers.
- FIX (header correctness): If we mutate the JSON body to inject `ver`, drop any
  pre-existing `Content-Length` so Django/WSGI recalculates it and avoids mismatch.
- HARDENING (spec validator + provider comment): Validate delegate JSON shape and, on
  provider errors or malformed payloads, return a deterministic local preview success
  payload. Also ensure `<!-- provider: ... -->` is present in result.html.
- TELEMETRY (non-PII): Add tiny in-process counters to distinguish provider-success vs
  local-fallback paths. Snapshot is logged after each bump as
  `[PPA][preview][telemetry] ...` with only counts (no request data).
- NOTE: Provider behavior is otherwise untouched; we only normalize the response to
  meet the stable endpoint contract.
"""

from __future__ import annotations  # CHANGED:

import logging  # CHANGED:
import json  # CHANGED:
import os  # CHANGED:
from typing import Any  # CHANGED:

from django.http import HttpRequest, HttpResponse, JsonResponse  # CHANGED:
from django.views.decorators.csrf import csrf_exempt  # CHANGED:

from . import (  # CHANGED:
    _json_response,
    _normalize_header_value,
    _ppa_key_ok,
    _with_cors,
)
from . import VERSION  # CHANGED:

log = logging.getLogger("webdoctor")  # CHANGED:
__all__ = ["preview"]  # CHANGED:

try:
    from . import preview_post as _pp  # type: ignore  # CHANGED:
except Exception:  # pragma: no cover
    _pp = None  # CHANGED:

# ---------- Tiny non-PII telemetry (process-local) ----------
from threading import Lock  # CHANGED:
_TELEMETRY = {  # CHANGED:
    "provider_ok": 0,         # successful delegate JSON returning valid contract
    "delegate_bad": 0,        # delegate present but returned non-JSON/invalid shape/error
    "fallback_local": 0,      # responses served by local fallback (with ok:true result)
    "provider_absent": 0,     # provider module not installed; wrapper served fallback
    "forced_fallback": 0,     # operator forced fallback via env flag
}  # CHANGED:
_TLOCK = Lock()  # CHANGED:

def _telemetry_bump(kind: str) -> None:  # CHANGED:
    """Increment a telemetry counter and log a snapshot (no secrets, no request data)."""  # CHANGED:
    try:
        with _TLOCK:
            _TELEMETRY[kind] = int(_TELEMETRY.get(kind, 0)) + 1
            snap = dict(_TELEMETRY)
        log.info(
            "[PPA][preview][telemetry] provider_ok=%s delegate_bad=%s fallback_local=%s provider_absent=%s forced_fallback=%s",
            snap.get("provider_ok", 0), snap.get("delegate_bad", 0), snap.get("fallback_local", 0),
            snap.get("provider_absent", 0), snap.get("forced_fallback", 0)
        )
    except Exception:
        # Telemetry must never break the endpoint.
        pass


def _truthy_env(name: str) -> bool:  # CHANGED:
    """Return True if environment variable is a common truthy value."""  # CHANGED:
    val = (os.getenv(name) or "").strip().lower()  # CHANGED:
    return val in {"1", "true", "yes", "force"}  # CHANGED:


def _log_preview_auth(request: HttpRequest) -> None:  # CHANGED:
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected_len = 0
    try:
        from django.conf import settings
        expected = _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))
        expected_len = len(expected)
        match = bool(expected) and (provided == expected)
    except Exception:
        match = False
    log.info("[PPA][preview][auth] expected_len=%s provided_len=%s match=%s origin=%s",
             expected_len, len(provided), match, _normalize_header_value(request.META.get("HTTP_ORIGIN")))


def _provider_label() -> str:  # CHANGED:
    """
    Heuristic label used in the injected HTML comment. Prefer explicit env config;
    detect operator-forced fallback; otherwise fall back to 'delegate'.
    """
    if _truthy_env("PPA_PREVIEW_FORCE_FALLBACK"):  # CHANGED:
        return "forced"  # CHANGED:
    val = (os.getenv("PPA_PREVIEW_PROVIDER") or "").strip().lower()
    if val in ("openai", "anthropic", "auto"):
        return val
    return "delegate"


def _ensure_provider_comment(html: str) -> str:  # CHANGED:
    """Append a benign provider marker if not already present to aid diagnostics."""
    try:
        marker = "<!-- provider:"
        if marker in html:
            return html
        return f"{html.rstrip()}<!-- provider: {_provider_label()} -->"
    except Exception:
        return html


def _local_fallback_success_payload() -> dict[str, Any]:  # CHANGED:
    """Deterministic local preview per spec when provider misbehaves or is down."""
    return {
        "ok": True,
        "result": {
            "title": "PostPress AI Preview (Provider Fallback)",
            "html": _ensure_provider_comment(
                "<p>Preview not available; provider offline.</p>"
            ),
            "summary": "Local fallback summary.",
        },
        "ver": VERSION,
    }


def _delegate_payload_needs_fallback(data: Any, status_code: int) -> bool:  # CHANGED:
    """
    Validate the stable contract on the delegate JSON:
      - HTTP status must be 2xx;
      - Body must be a dict with ok:true and result containing title/html/summary.
    """
    if not (200 <= int(status_code) < 300):
        return True
    if not isinstance(data, dict):
        return True
    if data.get("ok") is not True:
        return True
    res = data.get("result")
    if not isinstance(res, dict):
        return True
    for key in ("title", "html", "summary"):
        if key not in res or not isinstance(res[key], str) or not res[key]:
            return True
    return False


def _inject_ver_html_and_return(resp: HttpResponse, request: HttpRequest) -> HttpResponse:  # CHANGED:
    """
    Post-process a *valid* delegate response ONLY to:
      - ensure `ver` exists,
      - ensure result.html has the provider marker,
      - reflect allowed CORS,
      - clear Content-Length if we changed the body.
    """
    mutated = False
    try:
        ct = (resp.headers.get("Content-Type") or resp.get("Content-Type") or "").lower()
        if "application/json" not in ct:
            return _with_cors(resp, request)
        raw = resp.content.decode("utf-8", errors="replace")
        data = json.loads(raw)
        if isinstance(data, dict):
            # Ensure ver
            if "ver" not in data:
                data["ver"] = VERSION
                mutated = True
            # Ensure provider marker in result.html
            res = data.get("result")
            if isinstance(res, dict) and isinstance(res.get("html"), str):
                new_html = _ensure_provider_comment(res["html"])
                if new_html != res["html"]:
                    res["html"] = new_html
                    mutated = True
            if mutated:
                new_body = json.dumps(data).encode("utf-8")
                resp.content = new_body
                try:
                    del resp["Content-Length"]
                except Exception:
                    pass
    except Exception:
        # Do not fail delegate responses due to post-processing errors.
        pass
    return _with_cors(resp, request)


@csrf_exempt  # CHANGED:
def preview(request: HttpRequest) -> JsonResponse | HttpResponse:  # CHANGED:
    log.info("[PPA][preview][entry] host=%s origin=%s",
             _normalize_header_value(request.META.get("HTTP_HOST")),
             _normalize_header_value(request.META.get("HTTP_ORIGIN")))
    _log_preview_auth(request)

    # Always answer CORS preflight, even if a delegate exists.                                   # CHANGED:
    if request.method == "OPTIONS":  # CHANGED:
        return _with_cors(HttpResponse(status=204), request)  # CHANGED:

    # Operator drill: force local fallback regardless of provider availability.
    if _truthy_env("PPA_PREVIEW_FORCE_FALLBACK"):
        if request.method != "POST":
            return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)
        if not _ppa_key_ok(request):
            return _json_response({"ok": False, "error": "forbidden"}, 403, request)
        _telemetry_bump("forced_fallback")
        _telemetry_bump("fallback_local")
        return _json_response(_local_fallback_success_payload(), 200, request)

    # If a provider delegate exists, hand off immediately; then validate/normalize
    # according to the stable contract and spec.
    if _pp and hasattr(_pp, "preview"):
        # NEW: guard the delegate call so provider exceptions don't 500 the endpoint.          # CHANGED:
        try:  # CHANGED:
            delegate_resp: HttpResponse = _pp.preview(request)  # type: ignore
        except Exception as exc:  # CHANGED:
            log.exception("[PPA][preview][delegate_crash] %s", exc)  # CHANGED:
            _telemetry_bump("delegate_bad")  # CHANGED:
            _telemetry_bump("fallback_local")  # CHANGED:
            return _json_response(_local_fallback_success_payload(), 200, request)  # CHANGED:

        # Try to parse delegate JSON to decide if we need local fallback.
        try:
            status_code = int(getattr(delegate_resp, "status_code", 200))
            ct = (delegate_resp.headers.get("Content-Type") or delegate_resp.get("Content-Type") or "").lower()
            if "application/json" in ct:
                raw = delegate_resp.content.decode("utf-8", errors="replace")
                data = json.loads(raw)
                if _delegate_payload_needs_fallback(data, status_code):
                    # Provider error or malformed shape → deterministic local success
                    _telemetry_bump("delegate_bad")
                    _telemetry_bump("fallback_local")
                    return _json_response(_local_fallback_success_payload(), 200, request)
                # Delegate payload is valid → inject ver/comment & return
                _telemetry_bump("provider_ok")
                return _inject_ver_html_and_return(delegate_resp, request)
            else:
                # Non-JSON delegate → treat as provider failure with local success
                _telemetry_bump("delegate_bad")
                _telemetry_bump("fallback_local")
                return _json_response(_local_fallback_success_payload(), 200, request)
        except Exception:
            # Any unexpected error in inspection → safe local success
            _telemetry_bump("delegate_bad")
            _telemetry_bump("fallback_local")
            return _json_response(_local_fallback_success_payload(), 200, request)

    # Local wrapper behavior (only runs if provider module is absent).
    if request.method != "POST":
        return _json_response({"ok": False, "error": "method.not_allowed"}, 405, request)

    # Enforce X-PPA-Key on the fallback path to keep contract consistent.
    if not _ppa_key_ok(request):
        return _json_response({"ok": False, "error": "forbidden"}, 403, request)

    # Deterministic local preview result when providers are unavailable.
    _telemetry_bump("fallback_local")
    _telemetry_bump("provider_absent")
    return _json_response(_local_fallback_success_payload(), 200, request)
