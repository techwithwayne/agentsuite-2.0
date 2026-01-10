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

2026-01-10.1  # CHANGED:
- ADD: Command Center wiring (Customer + Plan + Subscription + Entitlement + EmailLog).      # CHANGED:
- ADD: Idempotent email send (Stripe retries won’t spam).                                   # CHANGED:
- KEEP: Existing License enforcement/shape untouched.                                       # CHANGED:
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

# CHANGED: Command Center models
from postpress_ai.models.customer import Customer  # CHANGED:
from postpress_ai.models.plan import Plan, seed_default_plans  # CHANGED:
from postpress_ai.models.subscription import Subscription  # CHANGED:
from postpress_ai.models.entitlement import Entitlement  # CHANGED:
from postpress_ai.models.email_log import EmailLog  # CHANGED:

log = logging.getLogger("webdoctor")

WEBHOOK_VER = "stripe-webhook.v2026-01-10.1"  # CHANGED:
LICENSE_EMAIL_SUBJECT = "Welcome to PostPress AI — here’s your key"  # CHANGED:


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


# --------------------------------------------------------------------------------------
# CHANGED: Command Center helpers (Customer/Plan/Subscription/Entitlement/EmailLog)
# --------------------------------------------------------------------------------------


def _split_name(full_name: str) -> tuple[str, str]:  # CHANGED:
    full_name = (full_name or "").strip()  # CHANGED:
    if not full_name:  # CHANGED:
        return "", ""  # CHANGED:
    parts = full_name.split()  # CHANGED:
    first = parts[0] if parts else ""  # CHANGED:
    last = " ".join(parts[1:]) if len(parts) > 1 else ""  # CHANGED:
    return first, last  # CHANGED:


def _upsert_customer_from_order(order: Order) -> Customer:  # CHANGED:
    """
    Create/update Customer using Order identity fields.
    """
    email = (order.purchaser_email or "").strip().lower()  # CHANGED:
    if not email:  # CHANGED:
        raise RuntimeError("Order missing purchaser_email; cannot upsert Customer.")  # CHANGED:

    first, last = _split_name(order.purchaser_name or "")  # CHANGED:

    customer, _created = Customer.objects.update_or_create(  # CHANGED:
        email=email,
        defaults={
            "first_name": first,
            "last_name": last,
            "source": "stripe_webhook",
        },
    )
    # Touch last_seen_at (support visibility)  # CHANGED:
    try:  # CHANGED:
        customer.last_seen_at = getattr(order, "updated_at", None)  # CHANGED:
        customer.save(update_fields=["last_seen_at"])  # CHANGED:
    except Exception:
        pass  # CHANGED:
    return customer  # CHANGED:


def _resolve_plan_code(metadata: dict[str, Any]) -> str:  # CHANGED:
    """
    Best-effort plan selection from Stripe metadata.
    We keep "tier" normalized to Tyler, but plan selection can still vary.

    Supported metadata keys (first match wins):
    - plan_code
    - plan
    - ppa_plan
    - product_tier
    - tier

    Defaults to "solo".
    """
    md = metadata or {}  # CHANGED:
    for k in ["plan_code", "plan", "ppa_plan", "product_tier", "tier"]:  # CHANGED:
        v = (md.get(k) or "").strip().lower()  # CHANGED:
        if v:
            return v  # CHANGED:
    return "solo"  # CHANGED:


def _resolve_plan(plan_code: str) -> Plan:  # CHANGED:
    """
    Map plan_code to a Plan row. Seed defaults if missing.
    """
    seed_default_plans()  # CHANGED:
    code = (plan_code or "").strip().lower() or "solo"  # CHANGED:

    # Normalize common aliases  # CHANGED:
    alias = {  # CHANGED:
        "unlimited": "agency_unlimited_byo",
        "agency_unlimited": "agency_unlimited_byo",
        "agency-byo": "agency_unlimited_byo",
        "byo": "agency_unlimited_byo",
    }.get(code)
    if alias:
        code = alias  # CHANGED:

    plan = Plan.objects.filter(code=code).first()  # CHANGED:
    if plan:
        return plan  # CHANGED:

    # Fallback: keep fulfillment moving  # CHANGED:
    return Plan.objects.get(code="solo")  # CHANGED:


def _upsert_subscription_for_session(  # CHANGED:
    *,
    customer: Customer,
    plan: Plan,
    session_obj: dict[str, Any],
) -> Subscription:
    """
    Create/update Subscription record idempotently by checkout session id.
    Even if mode='payment' (one-time), this remains useful as a command center record.
    """
    session_id = _safe_str(session_obj.get("id"))  # CHANGED:
    stripe_customer_id = _safe_str(session_obj.get("customer"))  # CHANGED:
    stripe_subscription_id = _safe_str(session_obj.get("subscription"))  # CHANGED:
    stripe_payment_intent_id = _safe_str(session_obj.get("payment_intent"))  # CHANGED:

    existing = Subscription.objects.filter(stripe_checkout_session_id=session_id).first()  # CHANGED:
    if existing:  # CHANGED:
        dirty = False  # CHANGED:
        if existing.customer_id != customer.id:
            existing.customer = customer
            dirty = True
        if existing.plan_id != plan.id:
            existing.plan = plan
            dirty = True
        if stripe_customer_id and existing.stripe_customer_id != stripe_customer_id:
            existing.stripe_customer_id = stripe_customer_id
            dirty = True
        if stripe_subscription_id and existing.stripe_subscription_id != stripe_subscription_id:
            existing.stripe_subscription_id = stripe_subscription_id
            dirty = True
        if stripe_payment_intent_id and existing.stripe_payment_intent_id != stripe_payment_intent_id:
            existing.stripe_payment_intent_id = stripe_payment_intent_id
            dirty = True
        if existing.status != Subscription.STATUS_ACTIVE:
            existing.status = Subscription.STATUS_ACTIVE
            dirty = True
        if dirty:
            existing.save()
        return existing  # CHANGED:

    return Subscription.objects.create(  # CHANGED:
        customer=customer,
        plan=plan,
        status=Subscription.STATUS_ACTIVE,
        stripe_customer_id=stripe_customer_id or "",
        stripe_subscription_id=stripe_subscription_id or "",
        stripe_payment_intent_id=stripe_payment_intent_id or "",
        stripe_checkout_session_id=session_id or "",
        meta={},
    )


def _ensure_entitlement(  # CHANGED:
    *,
    customer: Customer,
    plan: Plan,
    lic: License,
    sub: Subscription,
) -> Entitlement:
    """
    Create entitlement idempotently (one per license).
    """
    existing = Entitlement.objects.filter(license=lic).first()  # CHANGED:
    if existing:
        dirty = False  # CHANGED:
        if existing.customer_id != customer.id:
            existing.customer = customer
            dirty = True
        if existing.plan_id != plan.id:
            existing.plan = plan
            dirty = True
        if existing.subscription_id != sub.id:
            existing.subscription = sub
            dirty = True
        if existing.status != Entitlement.STATUS_ACTIVE:
            existing.status = Entitlement.STATUS_ACTIVE
            dirty = True
        if dirty:
            existing.save()
        return existing  # CHANGED:

    return Entitlement.objects.create(  # CHANGED:
        customer=customer,
        plan=plan,
        subscription=sub,
        license=lic,
        status=Entitlement.STATUS_ACTIVE,
        meta={},
    )


def _email_already_sent(event_id: str, to_email: str) -> bool:  # CHANGED:
    """
    Prevent duplicate email sends on Stripe webhook retries.
    """
    event_id = (event_id or "").strip()  # CHANGED:
    to_email = (to_email or "").strip().lower()  # CHANGED:
    if not event_id or not to_email:
        return False  # CHANGED:
    return EmailLog.objects.filter(
        email_type=EmailLog.TYPE_LICENSE_KEY,
        to_email=to_email,
        status=EmailLog.STATUS_SENT,
        meta__stripe_event_id=event_id,
    ).exists()  # CHANGED:


def _send_license_email_with_log(  # CHANGED:
    *,
    event_id: str,
    order: Order,
    lic: License,
    license_key: str,
    product_tier: str,
    customer: Optional[Customer] = None,
) -> bool:
    """
    Send license email once (idempotent), with EmailLog audit trail.
    Returns True if email was sent OR previously sent for this event.
    """
    to_email = (order.purchaser_email or "").strip().lower()  # CHANGED:
    if not to_email:
        return False  # CHANGED:

    if _email_already_sent(event_id, to_email):  # CHANGED:
        return True  # CHANGED: already sent on a previous retry

    elog = EmailLog.objects.create(  # CHANGED:
        customer=customer,
        to_email=to_email,
        subject=LICENSE_EMAIL_SUBJECT,
        email_type=EmailLog.TYPE_LICENSE_KEY,
        provider="sendgrid",
        status=EmailLog.STATUS_QUEUED,
        meta={
            "stripe_event_id": event_id,
            "order_id": getattr(order, "id", None),
            "license_id": getattr(lic, "id", None),
            "license_last4": (license_key or "")[-4:],
            "product_tier": product_tier,
        },
    )

    # Keep compatibility with your existing send_license_key_email signature.
    # If send_license_key_email supports subject in the future, we pass it; if not, we fallback.  # CHANGED:
    kwargs = {  # CHANGED:
        "to_email": to_email,
        "license_key": license_key,
        "purchaser_name": order.purchaser_name or None,
        "product_tier": product_tier,
        "subject": LICENSE_EMAIL_SUBJECT,  # CHANGED:
    }

    try:  # CHANGED:
        try:
            send_license_key_email(**kwargs)  # CHANGED:
        except TypeError:
            kwargs.pop("subject", None)  # CHANGED:
            send_license_key_email(**kwargs)  # CHANGED:

        elog.mark_sent()  # CHANGED:
        return True  # CHANGED:
    except Exception as e:
        elog.mark_failed(_safe_str(e))  # CHANGED:
        raise  # CHANGED: Stripe should retry during build/wiring phase


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
    - Command Center wiring (Customer/Plan/Subscription/Entitlement/EmailLog)

    Still intentionally deferred (later):
    - Checkout session creation
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
    # We still accept metadata for plan selection, but "tier" itself is normalized.  # CHANGED:
    _meta_tier = metadata.get("product_tier") or metadata.get("tier") or ""  # CHANGED:
    tier = "Tyler"  # CHANGED: locked normalization

    plan_code = _resolve_plan_code(metadata)  # CHANGED:

    log.info(
        "PPA Stripe webhook: checkout.session.completed session_id=%s payment_status=%s mode=%s email=%s tier=%s plan_code=%s amount_total=%s currency=%s",
        _safe_str(session_id),
        _safe_str(payment_status),
        _safe_str(mode),
        _safe_str(customer_email),
        _safe_str(tier),
        _safe_str(plan_code),
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
                "notes": (f"tier={_safe_str(tier)} plan_code={_safe_str(plan_code)}" if tier else None),
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
                tier_note = f"tier={_safe_str(tier)} plan_code={_safe_str(plan_code)}"
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

        # ---- Command Center wiring (idempotent-ish) ----
        customer: Optional[Customer] = None  # CHANGED:
        sub: Optional[Subscription] = None  # CHANGED:
        ent: Optional[Entitlement] = None  # CHANGED:

        if (order.purchaser_email or "").strip():  # CHANGED:
            customer = _upsert_customer_from_order(order)  # CHANGED:
            plan = _resolve_plan(plan_code)  # CHANGED:
            sub = _upsert_subscription_for_session(customer=customer, plan=plan, session_obj=obj)  # CHANGED:
            ent = _ensure_entitlement(customer=customer, plan=plan, lic=lic, sub=sub)  # CHANGED:

        # ---- Email (transactional + idempotent + logged) ----
        emailed = False  # CHANGED:
        if (order.purchaser_email or "").strip():  # CHANGED:
            emailed = _send_license_email_with_log(  # CHANGED:
                event_id=event_id,
                order=order,
                lic=lic,
                license_key=license_key,
                product_tier="Tyler",
                customer=customer,
            )  # CHANGED:

            # Mark order fulfilled once the license is emailed (or confirmed already emailed).  # CHANGED:
            if emailed and order.status != "fulfilled":  # CHANGED:
                order.status = "fulfilled"  # CHANGED:
                order.save(update_fields=["status", "updated_at"])  # CHANGED:
        else:
            # No email means no delivery — keep it visible for admin follow-up.  # CHANGED:
            if order.status != "paid_no_email":  # CHANGED:
                order.status = "paid_no_email"  # CHANGED:
                order.save(update_fields=["status", "updated_at"])  # CHANGED:

    log.info(  # CHANGED:
        "PPA Stripe webhook: license=%s created=%s emailed=%s key=%s",
        getattr(lic, "id", None),
        bool(created_license),
        bool(emailed),
        _mask_key(_safe_str(license_key)),
    )  # CHANGED:

    return {
        "event": "checkout.session.completed",
        "session_id": session_id,
        "payment_status": payment_status,
        "email": customer_email,
        "tier": "Tyler",
        "plan_code": plan_code,  # CHANGED:
        "order_db_id": order.id,
        "order_created": bool(created_order),
        "order_status": order.status,
        "license_db_id": getattr(lic, "id", None),
        "license_created": bool(created_license),
        "license_emailed": bool(emailed),
        "license_key_masked": _mask_key(_safe_str(license_key)),
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
