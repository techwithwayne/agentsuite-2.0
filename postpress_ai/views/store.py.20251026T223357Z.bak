# /home/techwithwayne/agentsuite/postpress_ai/views/store.py
"""
PostPress AI — /postpress-ai/store/ endpoint

CHANGE LOG
----------
2025-10-25 • Normalize-only implementation (no WP writes).                           # CHANGED:
2025-10-25 • Back-compat alias `store = store_view`.                                  # CHANGED:
2025-10-25 • Diagnostic header 'X-PPA-View: normalize' + ver:"1" on all responses.    # CHANGED:
2025-10-25 • Robust auth (trim quotes/whitespace, accept Bearer).                     # CHANGED:
2025-10-25 • On auth mismatch, expose non-secret debug headers (len + sha256).        # CHANGED:
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any, Dict, Tuple, Optional

from django.conf import settings
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("webdoctor")


def _with_diag_headers(resp: JsonResponse, auth_state: str = "") -> None:
    """Attach small diagnostic headers to prove routing/auth state."""
    try:
        resp["X-PPA-View"] = "normalize"
        if auth_state:
            # resp["X-PPA-Auth"] = auth_state  # disabled in prod
            pass
        resp["Cache-Control"] = "no-store"
    except Exception:
        pass


def _cors_reflect(resp: JsonResponse, req: HttpRequest) -> None:
    origin = req.headers.get("Origin") or req.META.get("HTTP_ORIGIN")
    try:
        allowed = getattr(settings, "PPA_ALLOWED_ORIGINS", []) or []
        if origin and origin in allowed:
            vary = resp.get("Vary", "")
            resp["Access-Control-Allow-Origin"] = origin
            resp["Vary"] = (vary + ", Origin").strip(", ")
            resp["Access-Control-Allow-Headers"] = (
                "Content-Type, X-PPA-Key, X-PPA-Install, X-PPA-Version, Authorization"
            )
            resp["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    except Exception:
        pass


def _clean(s: Optional[str]) -> str:
    """Trim whitespace and surrounding quotes."""
    s = (s or "").strip()
    if s.startswith(("'", '"')) and s.endswith(("'", '"')) and len(s) >= 2:
        s = s[1:-1]
    return s.strip()


def _auth_ok(req: HttpRequest) -> Tuple[bool, Optional[str] | Dict[str, str]]:
    """
    Validate client-sent key against settings.PPA_SHARED_KEY.

    Returns:
        (True, None) on success
        (False, "missing"|"server-misconfigured") on basic failures
        (False, {reason="mismatch", got_len, srv_len, got_sha, srv_sha}) on mismatch
    """
    shared_key = _clean(getattr(settings, "PPA_SHARED_KEY", "")) or ""
    if not shared_key:
        return False, "server-misconfigured"

    got = req.headers.get("X-PPA-Key") or req.META.get("HTTP_X_PPA_KEY") or None
    if not got:
        auth = req.headers.get("Authorization") or req.META.get("HTTP_AUTHORIZATION")
        if auth and auth.lower().startswith("bearer "):
            got = auth.split(" ", 1)[1]

    got = _clean(got)

    if not got:
        return False, "missing"

    if got != shared_key:
        return False, {
            "reason": "mismatch",
            "got_len": str(len(got)),
            "srv_len": str(len(shared_key)),
            "got_sha": sha256(got.encode()).hexdigest(),
            "srv_sha": sha256(shared_key.encode()).hexdigest(),
        }
    return True, None


def _json(req: HttpRequest) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse request JSON safely."""
    try:
        body = req.body.decode("utf-8") if req.body else ""
    except Exception:
        return None, "decode-error"
    if not body:
        return None, "empty"
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            return None, "non-object"
        return data, None
    except json.JSONDecodeError:
        return None, "invalid-json"
    except Exception:
        return None, "json-unknown"


def _s(s: Any) -> str:
    return (str(s or "")).strip()


def _normalize_status(raw: str) -> str:
    allowed = {"draft", "publish", "pending", "private"}
    s = (raw or "").strip().lower()
    return s if s in allowed else "draft"


def _normalize_store_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    title = _s(data.get("title") or data.get("subject"))
    content = _s(data.get("content") or data.get("html") or data.get("body"))
    excerpt = _s(data.get("excerpt") or data.get("summary"))
    status = _normalize_status(_s(data.get("status")))
    slug = _s(data.get("slug"))
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    categories = data.get("categories") if isinstance(data.get("categories"), list) else []
    author = _s(data.get("author"))
    return {
        "title": title,
        "content": content,
        "excerpt": excerpt,
        "status": status,
        "slug": slug or "",
        "tags": tags,
        "categories": categories,
        "author": author,
        "provider": "django",
    }


@csrf_exempt
def store_view(req: HttpRequest) -> HttpResponse:
    """
    POST /postpress-ai/store/
    Auth: X-PPA-Key: <key>  or  Authorization: Bearer <key>
    Body JSON: {title, content|html|body, excerpt|summary, status, slug, tags[], categories[], author}
    Returns: { ok:true, result:{...normalized...}, ver:"1" }
    """
    # OPTIONS preflight
    if req.method == "OPTIONS":
        resp = JsonResponse({"ok": True, "ver": "1", "mode": "preflight"})
        _with_diag_headers(resp, "options")
        _cors_reflect(resp, req)
        return resp

    # Method guard
    if req.method != "POST":
        resp = JsonResponse(
            {"ok": False, "error": "method-not-allowed", "allow": ["POST"], "ver": "1"},
            status=405,
        )
        _with_diag_headers(resp, "method")
        _cors_reflect(resp, req)
        return resp

    # Auth check
    ok, reason = _auth_ok(req)
    if not ok:
        status = 401
        auth_state = "fail:missing"
        extra: Dict[str, str] = {}
        if isinstance(reason, dict) and reason.get("reason") == "mismatch":
            status = 403
            auth_state = "fail:mismatch"
            extra = reason
        elif reason == "server-misconfigured":
            status = 500
            auth_state = "fail:server-misconfigured"

        resp = JsonResponse({"ok": False, "error": f"auth-{auth_state.split(':', 1)[-1]}", "ver": "1"}, status=status)
        if extra:
            # removed debug header
            # removed debug header
            # removed debug header
            # removed debug header
            pass
        _with_diag_headers(resp, auth_state)
        _cors_reflect(resp, req)
        return resp

    # JSON parse
    data, jerr = _json(req)
    if jerr:
        logger.info("PPA: /store bad JSON (%s), UA=%s", jerr, req.META.get("HTTP_USER_AGENT", "-"))
        resp = JsonResponse({"ok": False, "error": jerr, "ver": "1"}, status=400)
        _with_diag_headers(resp, "json")
        _cors_reflect(resp, req)
        return resp

    # Normalize & validate
    normalized = _normalize_store_payload(data)
    if not (normalized.get("content") or normalized.get("title")):
        logger.info("PPA: /store validation failure (missing title/content)")
        resp = JsonResponse({"ok": False, "error": "validation", "fields": ["title or content"], "ver": "1"}, status=400)
        _with_diag_headers(resp, "validation")
        _cors_reflect(resp, req)
        return resp

    # Success — return normalized payload; do NOT call WordPress from Django.
    logger.info("PPA: /store normalized payload (status=%s, provider=django)", normalized.get("status", "draft"))
    resp = JsonResponse({"ok": True, "result": normalized, "ver": "1"})
    _with_diag_headers(resp, "ok")
    _cors_reflect(resp, req)
    return resp


# Backwards-compatibility alias — some URLConfs reference `views.store`
store = store_view  # CHANGED
