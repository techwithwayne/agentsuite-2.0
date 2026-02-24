# /opt/render/project/src/postpress_ai/views/support.py

from __future__ import annotations

"""
PostPress AI — Support Agent Endpoints (Django)

PURPOSE
-------
Django-driven support endpoints for the WP Admin widget (PostPress AI pages only).

CHANGE LOG
----------
2026-02-24 • TONE: Support chat replies now speak in the Wayne vibe (calm, direct, human).  # CHANGED
           • BRAND: Support agent display name is "Yukia" and greeting uses "Hi, Yukia here."  # CHANGED
           • UX: Support chat responses are plain text (no Markdown tokens like **bold**).  # CHANGED
2026-02-23 • NEW: Scaffold Support endpoints (chat, account_status, action/*) with:
           - consistent JSON envelope
           - robust request parsing (JSON + form + legacy "payload" field)
           - conservative auth gate (shared secret) for server-to-server WP → Django calls
           - "not implemented yet" responses for action endpoints to prevent accidental money/key ops
2026-02-23 • FIX: Implement support_account_status by delegating to existing /license/verify/ logic
           (returns real payload; removes 501).  # CHANGED
2026-02-23 • FIX: Turn Support chat "online" (intent routing + account context detection) and
           include actionable next steps (upgrade/billing/tokens/license/troubleshoot) while keeping
           money/key operations gated behind explicit action endpoints.  # CHANGED
2026-02-23 • HARDEN: Internal delegate to /license/verify/ now forwards the same shared-secret auth headers
           as WP→Django calls to ensure consistent behavior.  # CHANGED
"""

import hashlib
import hmac
import importlib  # CHANGED
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

SUPPORT_AGENT_NAME = "Yukia"  # CHANGED

# License/account extraction fallbacks (lets WP send values in body OR headers OR query).
LICENSE_KEY_FIELDS = ("license_key", "key", "license")
SITE_URL_FIELDS = ("site_url", "install", "site")
HEADER_LICENSE_KEY = "HTTP_X_PPA_KEY"
HEADER_SITE_URL = "HTTP_X_PPA_INSTALL"


# -----------------------------
# Helpers (response envelope)
# -----------------------------

def _server_time_iso() -> str:
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
# Helpers (account extraction + delegation)
# -----------------------------

def _first_nonempty_str(v: Any) -> str:
    return str(v or "").strip()


def _extract_account_fields(request: HttpRequest, payload: Dict[str, Any]) -> Tuple[str, str]:
    """
    Bulletproof extraction for license_key + site_url.
    Supports:
      - JSON/body fields
      - query params (GET)
      - headers (X-PPA-Key / X-PPA-Install)
    """
    license_key = ""
    site_url = ""

    # 1) Payload fields
    for k in LICENSE_KEY_FIELDS:
        if k in payload:
            license_key = _first_nonempty_str(payload.get(k))
            if license_key:
                break
    for k in SITE_URL_FIELDS:
        if k in payload:
            site_url = _first_nonempty_str(payload.get(k))
            if site_url:
                break

    # 2) Query params (GET)
    if not license_key:
        for k in LICENSE_KEY_FIELDS:
            if k in request.GET:
                license_key = _first_nonempty_str(request.GET.get(k))
                if license_key:
                    break
    if not site_url:
        for k in SITE_URL_FIELDS:
            if k in request.GET:
                site_url = _first_nonempty_str(request.GET.get(k))
                if site_url:
                    break

    # 3) Headers
    if not license_key:
        license_key = _first_nonempty_str(request.META.get(HEADER_LICENSE_KEY))
    if not site_url:
        site_url = _first_nonempty_str(request.META.get(HEADER_SITE_URL))

    return license_key, site_url


def _delegate_to_license_verify(
    license_key: str,
    site_url: str,
    *,
    shared_secret: str = "",
) -> Tuple[Optional[JsonResponse], Optional[str]]:
    """
    Calls the existing /license/verify/ view internally and returns its JsonResponse as-is.
    """
    try:
        mod = importlib.import_module("postpress_ai.views.license")
    except Exception as e:
        return None, f"import postpress_ai.views.license failed: {e}"

    # Try a few likely names without assuming
    candidates = ("license_verify", "license_verify_v1", "license_verify_status", "license_verify_view")
    fn = None
    for name in candidates:
        f = getattr(mod, name, None)
        if callable(f):
            fn = f
            break

    if fn is None:
        return None, "license verify callable not found in postpress_ai.views.license"

    # Create an internal request to the view.
    try:
        from django.test.client import RequestFactory  # local import keeps module load conservative

        rf = RequestFactory()
        body = json.dumps({"license_key": license_key, "site_url": site_url})

        extra_headers = {
            "HTTP_X_PPA_KEY": license_key,
            "HTTP_X_PPA_INSTALL": site_url,
            "HTTP_X_PPA_VIEW": "support_account_status",
        }

        if shared_secret:
            extra_headers.update(
                {
                    "HTTP_X_PPA_SHARED_SECRET": shared_secret,
                    "HTTP_X_PPA_AUTH": shared_secret,
                    "HTTP_AUTHORIZATION": f"Bearer {shared_secret}",
                }
            )

        req = rf.post(
            "/postpress-ai/license/verify/",
            data=body,
            content_type="application/json",
            **extra_headers,
        )
        resp = fn(req)
        if isinstance(resp, JsonResponse):
            return resp, None

        try:
            content = getattr(resp, "content", b"") or b""
            code = int(getattr(resp, "status_code", 200))
            decoded = json.loads(content.decode("utf-8", errors="replace"))
            return JsonResponse(decoded, status=code), None
        except Exception:
            return None, "license verify returned non-JsonResponse and non-JSON content"
    except Exception as e:
        return None, f"delegate call failed: {e}"


# -----------------------------
# Helpers (Wayne vibe messages — PLAIN TEXT, NO MARKDOWN)
# -----------------------------

def _greeting() -> str:
    return f"Hi, {SUPPORT_AGENT_NAME} here. What's going on?"


def _msg_help_examples() -> str:
    return (
        f"{_greeting()}\n\n"
        "Try one of these:\n"
        "• upgrade my plan\n"
        "• buy more tokens\n"
        "• license won’t activate\n"
        "• I’m seeing an error in WordPress\n\n"
        "Next step: tell me what you clicked and what you expected to happen."
    )


def _msg_billing() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here — billing/plan stuff.\n\n"
        "Go to Account → Upgrade Plan.\n"
        "If it doesn’t open, what did you click and what did you expect to happen?"
    )


def _msg_tokens() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here — tokens.\n\n"
        "Go to Account → Buy Tokens.\n"
        "If it doesn’t open, what did you click and what did you expect to happen?"
    )


def _msg_license() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here — license help.\n\n"
        "Paste the exact message you see and the page you’re on.\n"
        "Next step: paste the message."
    )


def _msg_troubleshoot() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here — let’s diagnose it.\n\n"
        "Paste the exact error and the page it happens on.\n"
        "Next step: what changed right before it started?"
    )


def _msg_refund() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here — billing disputes/refunds.\n\n"
        "Email support@waynehatter.com with:\n"
        "• purchase email\n"
        "• amount + date\n"
        "• any receipt/invoice ID (if you have it)\n\n"
        "Next step: what did you click and what did you expect to happen?"
    )


def _msg_general() -> str:
    return (
        f"{SUPPORT_AGENT_NAME} here. Quick check so I don’t guess.\n\n"
        "Is this billing, tokens, license, or a site issue?\n"
        "Next step: one sentence — what you did + what you expected."
    )


# -----------------------------
# Helpers (very light router)
# -----------------------------

def _guess_intent(message: str) -> str:
    m = (message or "").lower().strip()
    if not m:
        return "unknown"

    if any(
        x in m
        for x in (
            "upgrade",
            "renew",
            "membership",
            "plan",
            "subscribe",
            "subscription",
            "cancel",
            "invoice",
            "billing",
            "portal",
        )
    ):
        return "billing"

    if any(x in m for x in ("refund", "charged", "charge", "money back")):
        return "refund"
    if any(x in m for x in ("license", "activation", "activate", "key")):
        return "license"
    if any(x in m for x in ("token", "credit", "out of tokens", "buy tokens")):
        return "tokens"
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
    thread_id = str(payload.get("thread_id") or payload.get("thread") or "").strip()

    license_key, site_url = _extract_account_fields(request, payload)
    has_context = bool(license_key and site_url)

    intent = _guess_intent(message)

    if not message:
        agent_message = _msg_help_examples()
    elif intent == "billing":
        agent_message = _msg_billing()
    elif intent == "tokens":
        agent_message = _msg_tokens()
    elif intent == "license":
        agent_message = _msg_license()
    elif intent == "troubleshoot":
        agent_message = _msg_troubleshoot()
    elif intent == "refund":
        agent_message = _msg_refund()
    else:
        agent_message = _msg_general()

    suggested_actions = []
    if intent == "billing":
        suggested_actions = [
            {
                "id": "go_to_upgrade_plan",
                "label": "Use the Upgrade Plan button on the Account screen",
                "kind": "ui_hint",
            }
        ]
    elif intent == "tokens":
        suggested_actions = [
            {
                "id": "go_to_buy_tokens",
                "label": "Use the Buy Tokens button on the Account screen",
                "kind": "ui_hint",
            }
        ]

    resp = {
        "agent": SUPPORT_AGENT_NAME,
        "intent": intent,
        "stage": "online",
        "agent_message": agent_message,
        "thread_id": thread_id,
        "echo": {
            "message_chars": len(message),
            "has_context": has_context,
        },
        "suggested_actions": suggested_actions,
        "router": "SupportRouter",  # CHANGED (debug only, safe add)
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

    license_key, site_url = _extract_account_fields(request, payload)
    if not license_key or not site_url:
        return _json_err(
            "invalid_payload",
            http_status=400,
            reason="missing license_key or site_url",
            user_message="Missing account identifiers. Please refresh the page and try again.",
        )

    resp, why = _delegate_to_license_verify(license_key, site_url, shared_secret=_expected_shared_secret())
    if resp is not None:
        return resp

    return _json_err(
        "account_status_failed",
        http_status=500,
        reason=why or "delegate failed",
        user_message="Account status is temporarily unavailable. Please try again in a moment.",
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

    confirm = bool(payload.get("confirm"))
    if not confirm:
        return _json_err(
            "confirm_required",
            http_status=400,
            reason="confirm flag missing",
            user_message="Refund requires confirm=true.",
        )

    return _json_err("not_implemented", http_status=501, reason="refund pending wiring")
