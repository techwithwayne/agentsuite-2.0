"""
postpress_ai.views.stripe_webhook

Stripe webhook endpoint (Django-only; fulfillment layer).
Stripe is used only for: payment success -> issue license key + email.

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

2025-12-26.2
- ADD: Persist Order on checkout.session.completed (idempotent by stripe_session_id).
- ADD: Store raw_event + raw_session snapshots for audit/debug.
- KEEP: No license issuance or email yet (intentionally deferred).

2025-12-26.3  # CHANGED:
- ADD: Issue License on checkout.session.completed (idempotent).                             # CHANGED:
- ADD: Email License key to purchaser (transactional).                                      # CHANGED:
- KEEP: Defensive mapping to existing License model fields (no guessing required fields).    # CHANGED:
- NOTE: Tier naming normalized to "Tyler" (product_tier metadata still allowed).             # CHANGED:
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import stripe

from django.db import models, transaction  # CHANGED:
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from postpress_ai.emailing import send_license_key_email  # CHANGED:
from postpress_ai.license_keys import generate_unique_license_key  # CHANGED:
from postpress_ai.models.license import License  # CHANGED:
from postpress_ai.models.order import Order

log = logging.getLogger("webdoctor")

WEBHOOK_VER = "stripe-webhook.v2025-12-26.3"  # CHANGED:


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


def _to_plain_dict(obj: Any) -> Dict[str, Any]:
    """
    Convert Stripe objects / mappings into a plain dict (best-effort).
    This avoids JSON serialization surprises and keeps our DB snapshots stable.
    """
    try:
        fn = getattr(obj, "to_dict", None)
        if callable(fn):
            return fn()
    except Exception:
        pass

    try:
        fn = getattr(obj, "to_dict_recursive", None)
        if callable(fn):
            return fn()
    except Exception:
        pass

    try:
        return dict(obj)
    except Exception:
        return {}


def _model_field_names(model_cls: type) -> set[str]:  # CHANGED:
    try:  # CHANGED:
        return {f.name for f in model_cls._meta.get_fields()}  # type: ignore[attr-defined]  # CHANGED:
    except Exception:  # CHANGED:
        return set()  # CHANGED:


def _pick_first_field(model_cls: type, candidates: list[str]) -> Optional[str]:  # CHANGED:
    names = _model_field_names(model_cls)  # CHANGED:
    for c in candidates:  # CHANGED:
        if c in names:  # CHANGED:
            return c  # CHANGED:
    return None  # CHANGED:


def _find_fk_to_order() -> Optional[str]:  # CHANGED:
    """
    Find a ForeignKey field on License that points to Order (if it exists).
    This lets us link License <-> Order without assuming field naming.
    """  # CHANGED:
    try:  # CHANGED:
        for f in License._meta.get_fields():  # type: ignore[attr-defined]  # CHANGED:
            if isinstance(f, models.ForeignKey) and getattr(f, "related_model", None) is Order:  # CHANGED:
                return f.name  # CHANGED:
    except Exception:  # CHANGED:
        return None  # CHANGED:
    return None  # CHANGED:


def _mask_key(k: str) -> str:  # CHANGED:
    k = (k or "").strip()  # CHANGED:
    if len(k) <= 8:  # CHANGED:
        return "***"  # CHANGED:
    return f"{k[:4]}…{k[-4:]}"  # CHANGED:


def _issue_or_get_license_for_order(  # CHANGED:
    *,
    order: Order,
    session_obj: Dict[str, Any],
    tier: str,
) -> Tuple[License, bool, str]:
    """
    Idempotently issues (or retrieves) a License tied to this Order/session.

    Returns: (license_obj, created_bool, license_key_str)
    """
    # 1) Figure out the key field name on your existing License model (defensive).  # CHANGED:
    key_field = _pick_first_field(License, ["license_key", "key", "code", "license", "license_code"])  # CHANGED:
    if not key_field:  # CHANGED:
        raise RuntimeError("License model has no recognizable key field (expected one of: license_key/key/code/...).")  # CHANGED:

    # 2) Figure out how to link License to Order/session (defensive).  # CHANGED:
    fk_order_field = _find_fk_to_order()  # CHANGED:
    session_id_field = _pick_first_field(License, ["stripe_session_id", "session_id", "stripe_checkout_session_id"])  # CHANGED:

    purchaser_email = order.purchaser_email or ""  # CHANGED:
    purchaser_name = order.purchaser_name or ""  # CHANGED:

    # 3) Idempotent lookup: prefer FK-to-Order if available; else fall back to session id if model supports it.  # CHANGED:
    existing: Optional[License] = None  # CHANGED:
    if fk_order_field:  # CHANGED:
        existing = License.objects.filter(**{fk_order_field: order}).first()  # CHANGED:
    elif session_id_field:  # CHANGED:
        existing = License.objects.filter(**{session_id_field: order.stripe_session_id}).first()  # CHANGED:

    if existing:  # CHANGED:
        license_key_value = _safe_str(getattr(existing, key_field, ""))  # CHANGED:
        return existing, False, license_key_value  # CHANGED:

    # 4) Generate a unique key against the chosen key field.  # CHANGED:
    def _exists(k: str) -> bool:  # CHANGED:
        return License.objects.filter(**{key_field: k}).exists()  # CHANGED:

    new_key = generate_unique_license_key(exists=_exists, prefix="PPA")  # CHANGED:

    # 5) Build create kwargs only for fields that actually exist on your License model.  # CHANGED:
    license_kwargs: dict[str, Any] = {key_field: new_key}  # CHANGED:

    # Link to order if possible.  # CHANGED:
    if fk_order_field:  # CHANGED:
        license_kwargs[fk_order_field] = order  # CHANGED:

    # Store session id if supported.  # CHANGED:
    if session_id_field:  # CHANGED:
        license_kwargs[session_id_field] = order.stripe_session_id  # CHANGED:

    # Common identity fields (best-effort).  # CHANGED:
    email_field = _pick_first_field(License, ["email", "customer_email", "purchaser_email"])  # CHANGED:
    name_field = _pick_first_field(License, ["name", "customer_name", "purchaser_name"])  # CHANGED:
    tier_field = _pick_first_field(License, ["tier", "product_tier", "plan", "edition"])  # CHANGED:
    status_field = _pick_first_field(License, ["status", "state"])  # CHANGED:

    if email_field and purchaser_email:  # CHANGED:
        license_kwargs[email_field] = purchaser_email  # CHANGED:
    if name_field and purchaser_name:  # CHANGED:
        license_kwargs[name_field] = purchaser_name  # CHANGED:
    if tier_field and tier:  # CHANGED:
        license_kwargs[tier_field] = tier  # CHANGED:
    if status_field:  # CHANGED:
        # Keep simple; your enforcement remains Django-authoritative elsewhere.  # CHANGED:
        license_kwargs[status_field] = "active"  # CHANGED:

    # Optional raw snapshots if your License model supports them.  # CHANGED:
    raw_field = _pick_first_field(License, ["raw", "raw_payload", "raw_session", "metadata"])  # CHANGED:
    if raw_field:  # CHANGED:
        license_kwargs[raw_field] = _to_plain_dict(session_obj)  # CHANGED:

    lic = License.objects.create(**license_kwargs)  # CHANGED:
    return lic, True, new_key  # CHANGED:


def _handle_checkout_session_completed(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fulfillment handler: checkout.session.completed

    This step:
    - Persist Order (idempotent)
    - Issue License (idempotent)
    - Email License key to purchaser (transactional)

    Still intentionally deferred (later):
    - Checkout session creation
    - Webhook → richer DB persistence / reporting
    """
    obj = (event.get("data") or {}).get("object") or {}

    session_id = obj.get("id")
    if not session_id:
        raise RuntimeError("Missing checkout session id in event payload.")

    customer_details = obj.get("customer_details") or {}
    customer_email = customer_details.get("email") or obj.get("customer_email")
    customer_name = customer_details.get("name")

    payment_status = obj.get("payment_status")
    mode = obj.get("mode")
    amount_total = obj.get("amount_total")
    currency = obj.get("currency")

    stripe_customer_id = obj.get("customer")
    stripe_payment_intent_id = obj.get("payment_intent")

    metadata = obj.get("metadata") or {}

    # Tier naming: EVERYTHING is Tyler now.  # CHANGED:
    # We still accept product metadata for future segmentation, but the top-level tier is "Tyler".  # CHANGED:
    meta_tier = metadata.get("product_tier") or metadata.get("tier") or ""  # CHANGED:
    tier = "Tyler" if not _safe_str(meta_tier).strip() else "Tyler"  # CHANGED: (hard normalized)

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

    event_id = _safe_str(event.get("id"))
    raw_event = _to_plain_dict(event)
    raw_session = _to_plain_dict(obj)

    normalized_status = "paid" if _safe_str(payment_status).lower() == "paid" else (_safe_str(payment_status) or "created")

    with transaction.atomic():
        # ---- Order upsert (idempotent by stripe_session_id) ----
        order, created_order = Order.objects.get_or_create(
            stripe_session_id=_safe_str(session_id),
            defaults={
                "stripe_event_id": event_id,
                "stripe_customer_id": _safe_str(stripe_customer_id) or None,
                "stripe_payment_intent_id": _safe_str(stripe_payment_intent_id) or None,
                "purchaser_name": _safe_str(customer_name) or None,
                "purchaser_email": _safe_str(customer_email) or None,
                "amount_total": amount_total if isinstance(amount_total, int) else None,
                "currency": _safe_str(currency) or None,
                "status": normalized_status,
                "raw_session": raw_session or None,
                "raw_event": raw_event or None,
                "notes": (f"tier={_safe_str(tier)}" if tier else None),
            },
        )

        if not created_order:
            dirty = False

            if event_id and not order.stripe_event_id:
                order.stripe_event_id = event_id
                dirty = True

            if stripe_customer_id and order.stripe_customer_id != _safe_str(stripe_customer_id):
                order.stripe_customer_id = _safe_str(stripe_customer_id)
                dirty = True
            if stripe_payment_intent_id and order.stripe_payment_intent_id != _safe_str(stripe_payment_intent_id):
                order.stripe_payment_intent_id = _safe_str(stripe_payment_intent_id)
                dirty = True

            if customer_name and order.purchaser_name != _safe_str(customer_name):
                order.purchaser_name = _safe_str(customer_name)
                dirty = True
            if customer_email and order.purchaser_email != _safe_str(customer_email):
                order.purchaser_email = _safe_str(customer_email)
                dirty = True

            if isinstance(amount_total, int) and order.amount_total != amount_total:
                order.amount_total = amount_total
                dirty = True
            if currency and order.currency != _safe_str(currency):
                order.currency = _safe_str(currency)
                dirty = True

            if normalized_status and order.status != normalized_status:
                order.status = normalized_status
                dirty = True

            if raw_session:
                order.raw_session = raw_session
                dirty = True
            if raw_event:
                order.raw_event = raw_event
                dirty = True

            if tier:
                tier_note = f"tier={_safe_str(tier)}"
                if not order.notes:
                    order.notes = tier_note
                    dirty = True
                elif tier_note not in order.notes:
                    order.notes = (order.notes + f"\n{tier_note}").strip()
                    dirty = True

            if dirty:
                order.save()

        # ---- License issuance (idempotent) ----
        lic, created_license, license_key = _issue_or_get_license_for_order(  # CHANGED:
            order=order, session_obj=obj, tier=tier  # CHANGED:
        )  # CHANGED:

        # ---- Email (transactional) ----
        emailed = False  # CHANGED:
        if (order.purchaser_email or "").strip():  # CHANGED:
            # If email sending fails, we raise and return 500 so Stripe retries (during this wiring phase).  # CHANGED:
            send_license_key_email(  # CHANGED:
                to_email=order.purchaser_email or "",  # CHANGED:
                license_key=license_key,  # CHANGED:
                purchaser_name=order.purchaser_name or None,  # CHANGED:
                product_tier="Tyler",  # CHANGED:
            )  # CHANGED:
            emailed = True  # CHANGED:
            # Mark order fulfilled once the license is emailed.  # CHANGED:
            if order.status != "fulfilled":  # CHANGED:
                order.status = "fulfilled"  # CHANGED:
                order.save(update_fields=["status", "updated_at"])  # CHANGED:
        else:
            # No email means no delivery — keep it visible for admin follow-up.  # CHANGED:
            if order.status != "paid_no_email":  # CHANGED:
                order.status = "paid_no_email"  # CHANGED:
                order.save(update_fields=["status", "updated_at"])  # CHANGED:

    log.info(  # CHANGED:
        "PPA Stripe webhook: license=%s created=%s emailed=%s key=%s",  # CHANGED:
        getattr(lic, "id", None),  # CHANGED:
        bool(created_license),  # CHANGED:
        bool(emailed),  # CHANGED:
        _mask_key(_safe_str(license_key)),  # CHANGED:
    )  # CHANGED:

    return {
        "event": "checkout.session.completed",
        "session_id": session_id,
        "payment_status": payment_status,
        "email": customer_email,
        "tier": "Tyler",
        "order_db_id": order.id,
        "order_created": bool(created_order),
        "order_status": order.status,
        "license_db_id": getattr(lic, "id", None),
        "license_created": bool(created_license),
        "license_emailed": bool(emailed),
        "license_key_masked": _mask_key(_safe_str(license_key)),  # CHANGED:
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
        return _json_response(
            False,
            error={"code": "missing_signature", "message": "Missing Stripe-Signature header."},
            status=400,
        )

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
            data = _handle_checkout_session_completed(_to_plain_dict(event))
            return _json_response(True, data=data, status=200)

        return _json_response(True, data={"event": event_type, "ignored": True}, status=200)

    except Exception as e:
        log.exception("PPA Stripe webhook: handler error type=%s", event_type)
        # During build, return 500 so Stripe retries.
        return _json_response(
            False,
            error={"code": "handler_error", "message": _safe_str(e), "event": event_type},
            status=500,
        )
