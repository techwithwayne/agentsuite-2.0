# /home/techwithwayne/agentsuite/postpress_ai/views/stripe_webhook.py
"""
PostPress AI — Stripe Webhook (Django-only fulfillment layer)
Path: postpress_ai/views/stripe_webhook.py

LOCKED INTENT
- Django is authoritative.
- WordPress never talks to Stripe.
- No CORS/browser changes.
- No JS work.
- Stripe retries must not duplicate licenses or emails.
- Email subject is locked in postpress_ai/emailing.py (do not change here).
- Keep Tyler normalization.
- Do NOT redesign Early Bird/license plumbing.

ENV VARS (LOCKED BEHAVIOR)
- PPA_STRIPE_MODE: "live" | "test"  (default: live)                         # CHANGED:
- STRIPE_LIVE_WEBHOOK_SECRET (preferred when mode=live)                      # CHANGED:
- STRIPE_TEST_WEBHOOK_SECRET (preferred when mode=test)                      # CHANGED:
- STRIPE_WEBHOOK_SECRET (fallback for legacy deployments)                     # CHANGED:

CHANGE LOG
- 2026-01-11: ADD mode-aware webhook secret selection via PPA_STRIPE_MODE and
             STRIPE_{LIVE|TEST}_WEBHOOK_SECRET with fallback STRIPE_WEBHOOK_SECRET.
             Log mode + env var name only; never log secret.                  # CHANGED:
- 2026-01-11: HARDEN EmailLog idempotency: lookup pre-migration safe (no column assumption)
             + IntegrityError guard for concurrent deliveries when unique constraint exists. # CHANGED:
- 2026-01-10: Webhook persists Order + License first, then Command Center wiring, then EmailLog + email.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

import stripe
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

WEBHOOK_VER = "stripe-webhook.v2026-01-11.1"  # CHANGED:


# ---------------------------
# Helpers (locked behavior)
# ---------------------------

def _get_stripe_webhook_secret_info() -> Tuple[str, str, str]:  # CHANGED:
    """
    Returns: (secret, source_env_var_name, mode)

    Required behavior:
    - Uses PPA_STRIPE_MODE in {"live","test"} (default: live)
    - Picks STRIPE_LIVE_WEBHOOK_SECRET or STRIPE_TEST_WEBHOOK_SECRET
    - Fallback to STRIPE_WEBHOOK_SECRET
    - NEVER logs the secret value
    """
    mode = (os.getenv("PPA_STRIPE_MODE") or "live").strip().lower()  # CHANGED:
    if mode not in ("live", "test"):  # CHANGED:
        mode = "live"  # CHANGED:

    primary = "STRIPE_LIVE_WEBHOOK_SECRET" if mode == "live" else "STRIPE_TEST_WEBHOOK_SECRET"  # CHANGED:
    secret = os.getenv(primary)  # CHANGED:
    source = primary  # CHANGED:

    if not secret:  # CHANGED:
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # CHANGED:
        source = "STRIPE_WEBHOOK_SECRET"  # CHANGED:

    if not secret:  # CHANGED:
        raise ImproperlyConfigured(
            f"Missing Stripe webhook secret. Set {primary} (preferred) or STRIPE_WEBHOOK_SECRET."
        )  # CHANGED:

    return secret, source, mode  # CHANGED:


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 6:
        return "PPA-…"
    return f"{key[:4]}-…{key[-4:]}"


def _model(app_label: str, model_name: str):
    """apps.get_model wrapper so we never depend on models/__init__.py exports."""
    return apps.get_model(app_label, model_name)


def _has_field(Model, field_name: str) -> bool:
    try:
        Model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _set_if_field(obj: Any, field_name: str, value: Any) -> None:
    """Set attribute only if model declares the field (defensive against schema drift)."""
    Model = obj.__class__
    if _has_field(Model, field_name):
        setattr(obj, field_name, value)


def _normalize_tier(raw: Optional[str]) -> str:
    """
    LOCKED: Keep Tyler normalization.
    Also supports plan fallback: missing metadata defaults to 'tyler' (solo -> tyler).
    """
    s = (raw or "").strip().lower()
    if not s:
        return "tyler"
    # Common variants
    if s in {"tyler", "early bird tyler", "tyler early bird", "solo", "earlybird", "early-bird"}:
        return "tyler"
    return s


def _derive_plan_code(tier: str) -> str:
    """
    LOCKED: Plan fallback.
    If tier is empty or unknown, default to 'tyler'.
    """
    tier = _normalize_tier(tier)
    return tier or "tyler"


def _derive_max_sites_from_plan(plan_obj: Any, fallback: int = 3) -> int:
    """
    Tyler Early Bird is confirmed: max_sites=3.
    We attempt to read plan.max_sites if it exists; else fallback to 3 for tyler.
    """
    if plan_obj is None:
        return fallback
    if hasattr(plan_obj, "max_sites") and isinstance(getattr(plan_obj, "max_sites"), int):
        return int(getattr(plan_obj, "max_sites"))
    return fallback


def _email_log_lookup_locked(to_email: str, stripe_event_id: str):  # CHANGED:
    """
    DB-level idempotency lookup.

    - If EmailLog has stripe_event_id column: query (fast)
    - Else: fallback scan meta['stripe_event_id'] in Python (pre-migration safe)

    Returns EmailLog instance or None.
    """
    if not to_email or not stripe_event_id:  # CHANGED:
        return None  # CHANGED:

    EmailLog = _model("postpress_ai", "EmailLog")  # CHANGED:

    has_col = False  # CHANGED:
    try:  # CHANGED:
        EmailLog._meta.get_field("stripe_event_id")  # CHANGED:
        has_col = True  # CHANGED:
    except Exception:  # CHANGED:
        has_col = False  # CHANGED:

    if has_col:  # CHANGED:
        return (
            EmailLog.objects.filter(to_email=to_email, stripe_event_id=stripe_event_id)  # CHANGED:
            .order_by("-id")  # CHANGED:
            .first()  # CHANGED:
        )

    # Pre-migration fallback: JSON lookups not supported on this backend, so scan in Python.  # CHANGED:
    qs = (
        EmailLog.objects.filter(to_email=to_email)  # CHANGED:
        .only("id", "meta")  # CHANGED:
        .order_by("-id")[:250]  # CHANGED: bounded scan
    )
    for row in qs:  # CHANGED:
        ev = (row.meta or {}).get("stripe_event_id")  # CHANGED:
        if ev == stripe_event_id:  # CHANGED:
            return row  # CHANGED:

    return None  # CHANGED:


def _send_license_key_email_best_effort(
    to_email: str,
    customer_name: str,
    license_key: str,
    tier: str,
    max_sites: int,
) -> str:
    """
    Lazy import to avoid circular imports (LOCKED).
    Returns provider message id if the underlying sender returns one.
    """
    from postpress_ai.emailing import send_license_key_email  # lazy import (LOCKED)

    # Try a few compatible calling conventions (keeps us resilient to signature changes).
    # We do NOT change the locked subject line here; emailing.py owns it.
    try:
        return str(
            send_license_key_email(
                to_email=to_email,
                name=customer_name,
                license_key=license_key,
                tier=tier,
                max_sites=max_sites,
            )
        )
    except TypeError:
        pass

    try:
        return str(
            send_license_key_email(
                to_email,
                license_key,
                tier=tier,
                max_sites=max_sites,
                name=customer_name,
            )
        )
    except TypeError:
        pass

    # Minimal fallback
    return str(send_license_key_email(to_email=to_email, license_key=license_key))


# ---------------------------
# Main webhook
# ---------------------------

@csrf_exempt
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """
    Stripe webhook receiver with signature verification.
    Handles: checkout.session.completed

    Idempotency:
    - Order + License: enforced by unique Stripe session id (model-level or logic-level).
    - EmailLog + email: DB-level via unique (stripe_event_id, to_email) when migration applied,
      with pre-migration safety fallback + IntegrityError guard for concurrency.            # CHANGED:
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed", "ver": WEBHOOK_VER}, status=405)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    # Mode-aware secret selection (LOCKED)  # CHANGED:
    endpoint_secret, secret_source, mode = _get_stripe_webhook_secret_info()  # CHANGED:
    logger.info("PPA:stripe_webhook mode=%s secret_source=%s", mode, secret_source)  # CHANGED:

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=endpoint_secret)
    except ValueError:
        logger.warning("PPA:stripe_webhook invalid_payload")
        return JsonResponse({"ok": False, "error": "invalid_payload", "ver": WEBHOOK_VER}, status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning("PPA:stripe_webhook invalid_signature")
        return JsonResponse({"ok": False, "error": "invalid_signature", "ver": WEBHOOK_VER}, status=400)

    event_id = (event or {}).get("id", "")
    event_type = (event or {}).get("type", "")

    if event_type != "checkout.session.completed":
        # Acknowledge unhandled events (Stripe expects 2xx).
        return JsonResponse({"ok": True, "ver": WEBHOOK_VER, "data": {"event": event_type, "handled": False}})

    session = ((event or {}).get("data") or {}).get("object") or {}
    session_id = session.get("id", "")
    payment_status = session.get("payment_status", "")
    customer_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email") or ""
    customer_name = (session.get("customer_details") or {}).get("name") or ""

    # Metadata-driven tier, with locked fallback behavior
    md = session.get("metadata") or {}
    raw_tier = md.get("tier") or md.get("plan") or md.get("plan_code") or md.get("tier_name") or ""
    tier = _normalize_tier(raw_tier)
    plan_code = _derive_plan_code(tier)

    # Persist Order + License FIRST (LOCKED ordering)
    Order = _model("postpress_ai", "Order")
    License = _model("postpress_ai", "License")

    order_created = False
    license_created = False

    # Persist minimal snapshots for audit/debug (not secrets)
    raw_event_safe = None
    raw_session_safe = None
    try:
        raw_event_safe = json.loads(payload.decode("utf-8"))
    except Exception:
        raw_event_safe = {"id": event_id, "type": event_type}

    # Session already a dict-ish; ensure JSON serializable
    try:
        raw_session_safe = json.loads(json.dumps(session))
    except Exception:
        raw_session_safe = {"id": session_id, "payment_status": payment_status}

    with transaction.atomic():
        # --- Order upsert (idempotent by stripe_session_id) ---
        order = None
        if _has_field(Order, "stripe_session_id"):
            order, created = Order.objects.get_or_create(  # type: ignore
                stripe_session_id=session_id,
                defaults={},
            )
            order_created = bool(created)
        else:
            # Fallback: try a generic get_or_create if field names differ
            order = Order.objects.order_by("-id").first()

        if order is not None:
            _set_if_field(order, "email", customer_email)
            _set_if_field(order, "tier", tier)
            _set_if_field(order, "plan_code", plan_code)
            _set_if_field(order, "status", "fulfilled" if payment_status == "paid" else "pending")
            _set_if_field(order, "raw_event", raw_event_safe)
            _set_if_field(order, "raw_session", raw_session_safe)
            try:
                order.save()
            except Exception:
                # Keep webhook stable even if optional fields fail
                logger.exception("PPA:order_save_failed session=%s", session_id)

        # --- License upsert (idempotent by stripe_session_id) ---
        license_obj = None
        if _has_field(License, "stripe_session_id"):
            license_obj, created = License.objects.get_or_create(  # type: ignore
                stripe_session_id=session_id,
                defaults={},
            )
            license_created = bool(created)
        else:
            # If License links to Order, try that; else just grab the latest
            if _has_field(License, "order_id") and order is not None:
                license_obj, created = License.objects.get_or_create(  # type: ignore
                    order=order,
                    defaults={},
                )
                license_created = bool(created)
            else:
                license_obj = License.objects.order_by("-id").first()

        # Set license shape defensively
        if license_obj is not None:
            _set_if_field(license_obj, "email", customer_email)
            _set_if_field(license_obj, "tier", tier)
            _set_if_field(license_obj, "plan_code", plan_code)

            # Ensure Tyler max_sites=3 if present; plan model can override
            Plan = _model("postpress_ai", "Plan")
            plan_obj = None
            try:
                if _has_field(Plan, "code"):
                    plan_obj = Plan.objects.filter(code=plan_code).first()
            except Exception:
                plan_obj = None

            max_sites = _derive_max_sites_from_plan(plan_obj, fallback=3 if plan_code == "tyler" else 1)
            _set_if_field(license_obj, "max_sites", max_sites)

            # If model has a status/active flag, keep it consistent
            if payment_status == "paid":
                _set_if_field(license_obj, "status", "active")
                _set_if_field(license_obj, "is_active", True)

            # If License links to Order, keep it
            if order is not None:
                _set_if_field(license_obj, "order", order)

            try:
                license_obj.save()
            except Exception:
                logger.exception("PPA:license_save_failed session=%s", session_id)

    # Command Center wiring happens AFTER Order + License (LOCKED ordering)
    # Upserts are defensive: if your schema differs, we try not to explode.
    customer_db_id = None
    plan_db_id = None
    subscription_db_id = None
    entitlement_db_id = None

    try:
        Customer = _model("postpress_ai", "Customer")
        Plan = _model("postpress_ai", "Plan")
        Subscription = _model("postpress_ai", "Subscription")
        Entitlement = _model("postpress_ai", "Entitlement")

        # Customer upsert (email as natural key)
        customer_obj = None
        if customer_email and _has_field(Customer, "email"):
            customer_obj, _ = Customer.objects.get_or_create(email=customer_email, defaults={})  # type: ignore
            customer_db_id = getattr(customer_obj, "id", None)
            _set_if_field(customer_obj, "name", customer_name)
            try:
                customer_obj.save()
            except Exception:
                pass

        # Plan upsert (code as natural key)
        plan_obj = None
        if _has_field(Plan, "code"):
            plan_obj, _ = Plan.objects.get_or_create(code=plan_code, defaults={})  # type: ignore
            plan_db_id = getattr(plan_obj, "id", None)
            _set_if_field(plan_obj, "name", tier.title() if tier else plan_code.title())
            if plan_code == "tyler":
                _set_if_field(plan_obj, "max_sites", 3)
            try:
                plan_obj.save()
            except Exception:
                pass

        # Subscription upsert (best-effort)
        subscription_obj = None
        if customer_obj is not None and plan_obj is not None:
            if _has_field(Subscription, "customer") and _has_field(Subscription, "plan"):
                subscription_obj, _ = Subscription.objects.get_or_create(  # type: ignore
                    customer=customer_obj,
                    plan=plan_obj,
                    defaults={},
                )
                subscription_db_id = getattr(subscription_obj, "id", None)
                _set_if_field(subscription_obj, "status", "active" if payment_status == "paid" else "pending")
                try:
                    subscription_obj.save()
                except Exception:
                    pass

        # Entitlement upsert (best-effort)
        if subscription_obj is not None and _has_field(Entitlement, "subscription"):
            entitlement_obj, _ = Entitlement.objects.get_or_create(subscription=subscription_obj, defaults={})  # type: ignore
            entitlement_db_id = getattr(entitlement_obj, "id", None)
            if plan_code == "tyler":
                _set_if_field(entitlement_obj, "max_sites", 3)
            try:
                entitlement_obj.save()
            except Exception:
                pass

        # Link EmailLog to Customer later when we create it (if possible)

    except Exception:
        logger.exception("PPA:command_center_wiring_failed session=%s", session_id)

    # Email delivery (idempotent on Stripe retries)
    # 1) Check existing
    if customer_email and event_id:
        existing = _email_log_lookup_locked(to_email=customer_email, stripe_event_id=event_id)  # CHANGED:
        if existing:
            return JsonResponse(
                {
                    "ok": True,
                    "ver": WEBHOOK_VER,
                    "data": {
                        "event": event_type,
                        "session_id": session_id,
                        "payment_status": payment_status,
                        "email": customer_email,
                        "tier": tier.title() if tier else tier,
                        "plan_code": plan_code,
                        "order_created": order_created,
                        "license_created": license_created,
                        "license_emailed": True,
                        "email_skipped": True,
                        "email_reason": "EmailLog exists",
                        "customer_db_id": customer_db_id,
                        "plan_db_id": plan_db_id,
                        "subscription_db_id": subscription_db_id,
                        "entitlement_db_id": entitlement_db_id,
                    },
                }
            )

    # 2) Create EmailLog row first (winner sends)
    EmailLog = _model("postpress_ai", "EmailLog")
    elog = EmailLog()  # type: ignore

    # Link customer if possible
    try:
        if customer_db_id and _has_field(EmailLog, "customer_id"):
            _set_if_field(elog, "customer_id", customer_db_id)
    except Exception:
        pass

    _set_if_field(elog, "to_email", customer_email)
    _set_if_field(elog, "subject", "Welcome to PostPress AI — here’s your key")  # audit-only; emailing.py owns the actual subject
    _set_if_field(elog, "email_type", getattr(EmailLog, "TYPE_LICENSE_KEY", "license_key"))
    _set_if_field(elog, "status", getattr(EmailLog, "STATUS_QUEUED", "queued"))
    _set_if_field(elog, "provider", "sendgrid")
    _set_if_field(elog, "created_at", timezone.now())

    # Safe meta (do NOT store full license keys)
    meta: Dict[str, Any] = {}
    meta["stripe_event_id"] = event_id
    meta["stripe_session_id"] = session_id
    meta["plan_code"] = plan_code
    meta["tier"] = tier
    meta["payment_status"] = payment_status

    # Store masked key info for admin visibility
    license_key = ""
    max_sites = 3 if plan_code == "tyler" else 1
    try:
        if "license_obj" in locals() and license_obj is not None:
            # Common field names: key, license_key
            if hasattr(license_obj, "key"):
                license_key = str(getattr(license_obj, "key") or "")
            elif hasattr(license_obj, "license_key"):
                license_key = str(getattr(license_obj, "license_key") or "")
            if hasattr(license_obj, "max_sites"):
                try:
                    max_sites = int(getattr(license_obj, "max_sites") or max_sites)
                except Exception:
                    pass
    except Exception:
        pass

    meta["license_key_masked"] = _mask_key(license_key)
    meta["max_sites"] = max_sites

    _set_if_field(elog, "meta", meta)

    # Also set the new column if it exists (post-migration), without assuming it exists.  # CHANGED:
    try:  # CHANGED:
        _set_if_field(elog, "stripe_event_id", event_id)  # CHANGED:
    except Exception:  # CHANGED:
        pass  # CHANGED:

    try:
        # DB-level idempotency save (unique constraint may exist)  # CHANGED:
        elog.save()  # CHANGED:
    except IntegrityError:  # CHANGED:
        # Concurrent delivery already created it. Skip sending.  # CHANGED:
        logger.info("PPA:email_log idempotent hit (IntegrityError) to=%s event=%s", customer_email, event_id)  # CHANGED:
        return JsonResponse(  # CHANGED:
            {
                "ok": True,
                "ver": WEBHOOK_VER,
                "data": {
                    "event": event_type,
                    "session_id": session_id,
                    "payment_status": payment_status,
                    "email": customer_email,
                    "tier": tier.title() if tier else tier,
                    "plan_code": plan_code,
                    "order_created": order_created,
                    "license_created": license_created,
                    "license_emailed": False,
                    "email_skipped": True,
                    "email_reason": "unique_constraint",
                    "customer_db_id": customer_db_id,
                    "plan_db_id": plan_db_id,
                    "subscription_db_id": subscription_db_id,
                    "entitlement_db_id": entitlement_db_id,
                },
            }
        )

    # 3) Send email
    provider_msg_id = ""
    try:
        provider_msg_id = _send_license_key_email_best_effort(
            to_email=customer_email,
            customer_name=customer_name,
            license_key=license_key,
            tier=tier,
            max_sites=max_sites,
        )
        # Mark sent (if helper exists)
        try:
            if hasattr(elog, "mark_sent"):
                elog.mark_sent(provider_message_id=provider_msg_id or "")
            else:
                _set_if_field(elog, "status", getattr(EmailLog, "STATUS_SENT", "sent"))
                _set_if_field(elog, "provider_message_id", provider_msg_id or "")
                _set_if_field(elog, "sent_at", timezone.now())
                elog.save(update_fields=["status", "provider_message_id", "sent_at"])
        except Exception:
            pass

        license_emailed = True
    except Exception as e:
        logger.exception("PPA:send_email_failed to=%s session=%s", customer_email, session_id)
        try:
            if hasattr(elog, "mark_failed"):
                elog.mark_failed(str(e))
            else:
                _set_if_field(elog, "status", getattr(EmailLog, "STATUS_FAILED", "failed"))
                _set_if_field(elog, "error_message", (str(e) or "")[:5000])
                elog.save(update_fields=["status", "error_message"])
        except Exception:
            pass
        license_emailed = False

    # Stable response (your ops checks depend on this shape)
    return JsonResponse(
        {
            "ok": True,
            "ver": WEBHOOK_VER,
            "data": {
                "event": event_type,
                "session_id": session_id,
                "payment_status": payment_status,
                "email": customer_email,
                "tier": tier.title() if tier else tier,
                "plan_code": plan_code,
                "order_created": order_created,
                "order_status": "fulfilled" if payment_status == "paid" else "pending",
                "license_created": license_created,
                "license_emailed": license_emailed,
                "license_key_masked": _mask_key(license_key),
                "customer_db_id": customer_db_id,
                "plan_db_id": plan_db_id,
                "subscription_db_id": subscription_db_id,
                "entitlement_db_id": entitlement_db_id,
            },
        }
    )
