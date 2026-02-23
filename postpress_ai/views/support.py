# /opt/render/project/src/postpress_ai/views/support.py

from __future__ import annotations

"""
PostPress AI — Support Agent Endpoints (Django)

PURPOSE
-------
Django-driven support endpoints for the WP Admin widget (PostPress AI pages only).
This file is intentionally SAFE to add without wiring URLs yet.

CHANGE LOG
----------
2026-02-23 • NEW: Scaffold Support endpoints (chat, account_status, action/*) with:
           - consistent JSON envelope
           - robust request parsing (JSON + form + legacy "payload" field)
           - conservative auth gate (shared secret) for server-to-server WP → Django calls
           - "not implemented yet" responses for action endpoints to prevent accidental money/key ops
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt


# -----------------------------
# Config
# -----------------------------

MAX_BODY_BYTES = 256_000  # ~256KB hard cap to prevent abuse / accidental huge posts
AUTH_ENV_KEY = "PPA_WP_SHARED_SECRET"  # Shared secret stored in Django env (do NOT log it)
AUTH_HEADER_CANDIDATES = (
    "HTTP_X_PPA_SHARED_SECRET",
    "HTTP_X_PPA_AUTH",
    "HTTP_AUTHORIZATION",
)


# -----------------------------
# Helpers (response envelope)
# -----------------------------

def _server_time_iso() -> str:
    # CHANGED: Use epoch-based UTC ISO without importing pytz/dateutil.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_ok(data: Any = None, *, http_status: int = 200, audit_id: Optional[str] = None) -> JsonResponse:
    aid = audit_id or str(uuid.uuid4())
    payload = {
        "ok": True,
        "data": data if data is not None else {},
        "meta": {
            "audit_id": aid,
            "server_time": _server_time_iso(),
        },
    }
    return JsonResponse(payload, status=http_status)


def _json_err(
    error_code: str,
    *,
    http_status: int = 400,
    reason: str = "",
    user_message: str = "",
    audit_id: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> JsonResponse:
    aid = audit_id or str(uuid.uuid4())
    meta: Dict[str, Any] = {
        "error_code": error_code,
        "http_status": http_status,
        "server_time": _server_time_iso(),
    }
    if reason:
        meta["reason"] = reason
    if user_message:
        meta["user_message"] = user_message
    if extra_meta:
        meta.update(extra_meta)

    return JsonResponse({"ok": False, "data": {}, "meta": meta, "audit_id": aid}, status=http_status)


# -----------------------------
# Helpers (request parsing)
# -----------------------------

def _read_body_bytes(request: HttpRequest) -> Tuple[bytes, Optional[JsonResponse]]:
    body = request.body or b""
    if len(body) > MAX_BODY_BYTES:
        return b"", _json_err(
            "payload_too_large",
            http_status=413,
            reason=f"body_bytes>{MAX_BODY_BYTES}",
            user_message="That request was too large. Please try again with a shorter message.",
        )
    return body, None


def _parse_payload(request: HttpRequest) -> Tuple[Dict[str, Any], Optional[JsonResponse]]:
    """
    Accept:
      - application/json
      - x-www-form-urlencoded with JSON in `payload` (legacy compatibility)
      - x-www-form-urlencoded flat keys
    """
    body, too_big = _read_body_bytes(request)
    if too_big:
        return {}, too_big

    # Prefer JSON body if present
    if body.strip():
        try:
            decoded = body.decode("utf-8", errors="replace").strip()
            if decoded:
                return json.loads(decoded), None
        except Exception:
            # Fall through to form parsing
            pass

    # Form POST (including legacy: payload="<json>")
    if request.POST:
        if "payload" in request.POST:
            raw = (request.POST.get("payload") or "").strip()
            if raw:
                try:
                    return json.loads(raw), None
                except Exception:
                    return {}, _json_err(
                        "invalid_json",
                        http_status=400,
                        reason="form.payload not json",
                        user_message="I couldn't read that request. Please refresh and try again.",
                    )
        # Flat form fields
        return {k: request.POST.get(k) for k in request.POST.keys()}, None

    # Empty payload is allowed for some endpoints, but we'll return {}.
    return {}, None


# -----------------------------
# Helpers (auth)
# -----------------------------

def _expected_shared_secret() -> str:
    return (os.getenv(AUTH_ENV_KEY) or "").strip()


def _extract_presented_secret(request: HttpRequest, payload: Dict[str, Any]) -> str:
    # 1) Headers
    for hdr in AUTH_HEADER_CANDIDATES:
        val = (request.META.get(hdr) or "").strip()
        if not val:
            continue
        # Authorization: Bearer <token>
        if hdr == "HTTP_AUTHORIZATION" and val.lower().startswith("bearer "):
            return val.split(" ", 1)[1].strip()
        return val

    # 2) Body field fallback
    val2 = (payload.get("shared_secret") or payload.get("auth") or payload.get("api_key") or "")
    return str(val2).strip()


def _require_shared_secret(request: HttpRequest, payload: Dict[str, Any]) -> Optional[JsonResponse]:
    expected = _expected_shared_secret()
    if not expected:
        # Server misconfig: secret not set. Do NOT proceed.
        return _json_err(
            "server_misconfig",
            http_status=500,
            reason=f"{AUTH_ENV_KEY} missing",
            user_message="Support is temporarily unavailable. Please try again later.",
        )

    presented = _extract_presented_secret(request, payload)
    if not presented:
        return _json_err(
            "forbidden",
            http_status=403,
            reason="missing_key",
            user_message="Authentication missing. Please refresh the page and try again.",
        )

    if not hmac.compare_digest(presented, expected):
        return _json_err(
            "forbidden",
            http_status=403,
            reason="invalid_key",
            user_message="Authentication failed. Please refresh the page and try again.",
        )

    return None


# -----------------------------
# Helpers (very light router)
# -----------------------------

def _guess_intent(message: str) -> str:
    m = (message or "").lower().strip()
    if not m:
        return "unknown"
    if any(x in m for x in ("refund", "charged", "charge", "money back")):
        return "refund"
    if any(x in m for x in ("license", "activation", "activate", "key")):
        return "license"
    if any(x in m for x in ("token", "credit", "out of tokens", "buy tokens")):
        return "tokens"
    if any(x in m for x in ("billing", "invoice", "portal", "subscription", "cancel")):
        return "billing"
    if any(x in m for x in ("error", "broken", "not working", "failed", "bug")):
        return "troubleshoot"
    return "general"


# -----------------------------
# Views (Support endpoints)
# -----------------------------

@csrf_exempt
def support_chat(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")

    payload, err = _parse_payload(request)
    if err:
        return err

    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err

    message = str(payload.get("message") or "").strip()
    context = payload.get("context") or {}
    intent = _guess_intent(message)

    # NOTE: We are intentionally not calling the AI yet, because we haven't wired
    # the full policy, Stripe gates, and license tooling into these endpoints.
    # This keeps it safe while we finish wiring URLs + action implementations.
    resp = {
        "agent": "SupportRouter",
        "intent": intent,
        "stage": "bootstrapping",
        "agent_message": (
            "Support is coming online. I can see your message and your site context — "
            "next step is wiring these endpoints into routes and turning on the full router."
        ),
        "echo": {
            "message_chars": len(message),
            "has_context": isinstance(context, dict) and bool(context),
        },
        "next_actions": [
            "wire_urls",
            "enable_account_status",
            "enable_actions_safely",
        ],
    }
    return _json_ok(resp)


@csrf_exempt
def support_account_status(request: HttpRequest) -> JsonResponse:
    if request.method not in ("GET", "POST"):
        return _json_err("method_not_allowed", http_status=405, reason="GET/POST allowed")

    payload: Dict[str, Any] = {}
    if request.method == "POST":
        payload, err = _parse_payload(request)
        if err:
            return err

    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err

    # Placeholder until we wire into existing account/license/usage services.
    return _json_err(
        "not_implemented",
        http_status=501,
        reason="account_status pending wiring",
        user_message="Account status endpoint is not enabled yet.",
    )


@csrf_exempt
def support_action_create_checkout(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")
    payload, err = _parse_payload(request)
    if err:
        return err
    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err
    return _json_err("not_implemented", http_status=501, reason="checkout session pending wiring")


@csrf_exempt
def support_action_create_billing_portal(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")
    payload, err = _parse_payload(request)
    if err:
        return err
    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err
    return _json_err("not_implemented", http_status=501, reason="billing portal pending wiring")


@csrf_exempt
def support_action_issue_license_key(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")
    payload, err = _parse_payload(request)
    if err:
        return err
    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err
    return _json_err("not_implemented", http_status=501, reason="issue license key pending wiring")


@csrf_exempt
def support_action_replace_license_key(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")
    payload, err = _parse_payload(request)
    if err:
        return err
    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err
    return _json_err("not_implemented", http_status=501, reason="replace license key pending wiring")


@csrf_exempt
def support_action_refund(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_err("method_not_allowed", http_status=405, reason="POST required")
    payload, err = _parse_payload(request)
    if err:
        return err
    auth_err = _require_shared_secret(request, payload)
    if auth_err:
        return auth_err

    # Extra safety: never refund without explicit "confirm": true
    confirm = bool(payload.get("confirm"))
    if not confirm:
        return _json_err(
            "confirm_required",
            http_status=400,
            reason="confirm flag missing",
            user_message="Refund requires confirm=true.",
        )

    return _json_err("not_implemented", http_status=501, reason="refund pending wiring")