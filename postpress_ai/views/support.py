# /opt/render/project/src/postpress_ai/views/support.py

from __future__ import annotations

"""
PostPress AI — Support Agent Endpoints (Django)

PURPOSE
-------
Django-driven support endpoints for the WP Admin widget (PostPress AI pages only).

CHANGE LOG
----------
2026-02-24 • FIX: Implement locked Yukia support behavior (plain text replies, no agent-meta phrasing, token/credit intent routing, suggested_actions contract, exception fallback).  # CHANGED
2026-02-25 • FIX: Also return suggested_actions at the top-level JSON for WP UI button rendering (keeps data.suggested_actions for back-compat).  # CHANGED
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
# Helpers (Yukia Support Replies — PLAIN TEXT ONLY)
# -----------------------------

# NOTE:
# - WP UI owns the greeting line.
# - Messages returned here must be plain text only (no Markdown rendering, no emojis).
# - Avoid agent-meta phrasing inside all replies.

UNREACHABLE_MESSAGE = "I couldn’t reach support right now."

# Token/credit intent reply must be EXACT (including punctuation + line breaks).
TOKEN_INTENT_MESSAGE = "Okay, I see you’re asking about credits (tokens).\nPick one below:"

# Suggested-actions payload contract (exact shape; max 3; fixed order)
SUGGESTED_ACTIONS_TOKENS = [
    {"id": "buy_tokens", "label": "Buy Tokens"},
    {"id": "check_token_balance", "label": "Check My Token Balance"},
    {"id": "something_looks_wrong", "label": "Something Looks Wrong"},
]


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _is_ui_failure_something_looks_wrong(payload: Dict[str, Any]) -> bool:
    # WP may send an action id when the user clicks a suggested action.
    action_id = str(
        payload.get("action_id")
        or payload.get("action")
        or payload.get("suggested_action_id")
        or payload.get("suggested_action")
        or ""
    ).strip().lower()
    ui_event = str(payload.get("ui_event") or payload.get("event") or "").strip().lower()
    return action_id == "something_looks_wrong" or ui_event == "something_looks_wrong"


def _is_ui_failure_popup_blocked(payload: Dict[str, Any]) -> bool:
    ui_event = str(payload.get("ui_event") or payload.get("event") or "").strip().lower()
    return ui_event == "popup_blocked" or _as_bool(payload.get("popup_blocked"))


def _is_token_intent(message: str) -> bool:
    m = (message or "").lower().strip()
    if not m:
        return False

    # Tokens/credits/balance/usage/0 tokens
    token_terms = (
        "token",
        "tokens",
        "credit",
        "credits",
        "balance",
        "usage",
        "used",
        "remaining",
        "0 token",
        "0 tokens",
        "zero tokens",
        "no tokens",
        "out of tokens",
    )
    return any(t in m for t in token_terms)


def _chat_reply_for_message(message: str, payload: Dict[str, Any]) -> Tuple[str, str, list]:
    """
    Returns: (intent, agent_message, suggested_actions)
    """
    # True UI failure paths only
    if _is_ui_failure_something_looks_wrong(payload):
        return "something_looks_wrong", "What did you click, and what did you expect?", SUGGESTED_ACTIONS_TOKENS

    if _is_ui_failure_popup_blocked(payload):
        return "popup_blocked", "What did you click, and what did you expect?", SUGGESTED_ACTIONS_TOKENS

    # Token/credit intent (exact response)
    if _is_token_intent(message):
        return "tokens", TOKEN_INTENT_MESSAGE, SUGGESTED_ACTIONS_TOKENS

    # Default: keep it tight, drive to the 3 actions.
    return "general", "Pick one below:", SUGGESTED_ACTIONS_TOKENS
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

    try:
        message = str(payload.get("message") or "").strip()
        thread_id = str(payload.get("thread_id") or payload.get("thread") or "").strip()

        license_key, site_url = _extract_account_fields(request, payload)
        has_context = bool(license_key and site_url)

        intent, agent_message, suggested_actions = _chat_reply_for_message(message, payload)

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
        }
        # CHANGED: Provide suggested_actions at the top-level as well (WP UI expects this for rendering buttons outside the bubble).
        # Keep data.suggested_actions for backward compatibility.
        aid = str(uuid.uuid4())  # CHANGED:
        return JsonResponse(
            {
                "ok": True,
                "data": resp,
                "suggested_actions": suggested_actions,  # CHANGED:
                "meta": {"audit_id": aid, "server_time": _server_time_iso()},
            },
            status=200,
        )
    except Exception:
        # Unreachable/exception path must return ONLY this message (no click/expect line).
        resp = {
            "agent": SUPPORT_AGENT_NAME,
            "intent": "unreachable",
            "stage": "online",
            "agent_message": UNREACHABLE_MESSAGE,
            "thread_id": str(payload.get("thread_id") or payload.get("thread") or "").strip(),
            "suggested_actions": [],
        }
        # CHANGED: Provide suggested_actions top-level (empty) for UI consistency.
        aid = str(uuid.uuid4())  # CHANGED:
        return JsonResponse(
            {
                "ok": True,
                "data": resp,
                "suggested_actions": [],  # CHANGED:
                "meta": {"audit_id": aid, "server_time": _server_time_iso()},
            },
            status=200,
        )


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
