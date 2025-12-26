# /home/techwithwayne/agentsuite/postpress_ai/views/stripe_webhook.py
"""
postpress_ai.views.stripe_webhook

Stripe webhook endpoint (Django-only; fulfillment layer).
Stripe is used only for: payment success -> (later) issue license key + email.

LOCKED INTENT
- Django is authoritative.
- WordPress never talks to Stripe.
- No CORS widening. No browser→Django changes.

ENV VARS
- STRIPE_WEBHOOK_SECRET (required) : Stripe webhook signing secret (whsec_...)
- STRIPE_SECRET_KEY     (optional here; needed later for Checkout session creation)

======== CHANGE LOG ========
2025-12-26
- ADD: Stripe webhook receiver with signature verification.
- ADD: Minimal handler for checkout.session.completed (logs + returns stable JSON).
- NOTE: No DB writes yet. License issuance + email will be the next files.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import stripe

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

log = logging.getLogger("webdoctor")

WEBHOOK_VER = "stripe-webhook.v2025-12-26.1"


def _json_response(
    ok: bool,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
    status: int = 200,
) -> JsonResponse:
    return JsonResponse(
        {"ok": bool(ok), "ver": WEBHOOK_VER, "data": data or {}, "error": error or {}},
        status=status,
    )


def _get_stripe_webhook_secret() -> str:
    secret = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("Missing STRIPE_WEBHOOK_SECRET env var.")
    return secret


def _safe_str(val: Any) -> str:
    try:
        return str(val)
    except Exception:
        return ""


def _handle_checkout_session_completed(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimal v1 handler.

    Next step (next files):
    - persist order + customer
    - generate license key
    - email license key to purchaser
    """
    obj = (event.get("data") or {}).get("object") or {}

    session_id = obj.get("id")
    customer_email = obj.get("customer_details", {}).get("email") or obj.get("customer_email")
    payment_status = obj.get("payment_status")
    mode = obj.get("mode")
    amount_total = obj.get("amount_total")
    currency = obj.get("currency")

    metadata = obj.get("metadata") or {}
    tier = metadata.get("product_tier") or metadata.get("tier") or ""

    log.info(
        "PPA Stripe webhook: checkout.session.completed session_id=%s payment_status=%s mode=%s email=%s tier=%s amount_total=%s currency=%s",
        _safe_str(session_id),
        _safe_str(payment_status),
        _safe_str(mode),
        _safe_str(customer_email),
        _safe_str(tier),
        _safe_str(amount_total),
        _safe_str(currency),
    )

    return {
        "event": "checkout.session.completed",
        "session_id": session_id,
        "payment_status": payment_status,
        "email": customer_email,
        "tier": tier,
    }


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """
    Stripe webhook receiver (POST only).
    Verifies Stripe signature (required).
    """
    if request.method != "POST":
        return _json_response(False, error={"code": "method_not_allowed", "message": "POST required."}, status=405)

    try:
        secret = _get_stripe_webhook_secret()
    except Exception as e:
        log.error("PPA Stripe webhook misconfigured: %s", _safe_str(e))
        return _json_response(False, error={"code": "misconfigured", "message": "Webhook not configured."}, status=500)

    payload = request.body  # raw bytes
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    if not sig_header:
        return _json_response(False, error={"code": "missing_signature", "message": "Missing Stripe-Signature header."}, status=400)

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret)
    except ValueError:
        return _json_response(False, error={"code": "invalid_payload", "message": "Invalid JSON payload."}, status=400)
    except stripe.error.SignatureVerificationError:
        return _json_response(False, error={"code": "bad_signature", "message": "Signature verification failed."}, status=400)
    except Exception as e:
        log.exception("PPA Stripe webhook: verification error")
        return _json_response(False, error={"code": "verify_error", "message": _safe_str(e)}, status=500)

    event_type = _safe_str(event.get("type"))
    log.info("PPA Stripe webhook received: type=%s", event_type)

    try:
        if event_type == "checkout.session.completed":
            data = _handle_checkout_session_completed(event)
            return _json_response(True, data=data, status=200)

        return _json_response(True, data={"event": event_type, "ignored": True}, status=200)

    except Exception as e:
        log.exception("PPA Stripe webhook: handler error type=%s", event_type)
        # During build, return 500 so Stripe retries.
        return _json_response(False, error={"code": "handler_error", "message": _safe_str(e), "event": event_type}, status=500)
