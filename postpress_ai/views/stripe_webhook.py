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
- PPA_STRIPE_MODE: "live" | "test"  (default: live)                          # CHANGED:
- STRIPE_LIVE_WEBHOOK_SECRET (preferred when mode=live)                       # CHANGED:
- STRIPE_TEST_WEBHOOK_SECRET (preferred when mode=test)                       # CHANGED:
- STRIPE_WEBHOOK_SECRET (fallback for legacy deployments)                      # CHANGED:

CHANGE LOG
- 2026-02-26: FIX: Allow one endpoint to accept BOTH live + test/sandbox webhook signatures
             by trying multiple secrets in a safe order (env var names only; never log secrets).  # CHANGED:
- 2026-01-11: FIX: Remove stray CHANGE LOG text that got pasted into runtime code (syntax breaker).  # CHANGED:
- 2026-01-11: ADD mode-aware webhook secret selection via PPA_STRIPE_MODE and
             STRIPE_{LIVE|TEST}_WEBHOOK_SECRET with fallback STRIPE_WEBHOOK_SECRET.
             Log mode + env var name only; never log secret.                   # CHANGED:
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

WEBHOOK_VER = "stripe-webhook.v2026-02-26.1"  # CHANGED:


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


def _set_stripe_api_key_for_event(event: dict) -> Tuple[str, str]:  # CHANGED:
    """
    Choose Stripe secret key based on webhook event livemode.
    livemode=True  -> STRIPE_LIVE_SECRET_KEY (preferred)
    livemode=False -> STRIPE_SECRET_KEY (preferred)
    """
    is_live = bool((event or {}).get("livemode"))
    primary = "STRIPE_LIVE_SECRET_KEY" if is_live else "STRIPE_SECRET_KEY"
    fallback = "STRIPE_SECRET_KEY" if is_live else "STRIPE_LIVE_SECRET_KEY"

    key = (os.getenv(primary) or "").strip()
    source = primary

    if not key:
        key = (os.getenv(fallback) or "").strip()
        source = fallback

    if not key:
        raise ImproperlyConfigured(
            f"Missing Stripe secret key. Set {primary} (preferred) or {fallback}."
        )

    stripe.api_key = key
    logger.info(
        "PPA:stripe api_key_set livemode=%s source=%s key=%s",
        is_live,
        source,
        _mask_key(key),
    )
    return key, source


def _get_plan_slug_from_price(session_id: str) -> str:  # CHANGED:
    """
    Source of truth: Stripe Price metadata.plan_slug

    Reliable approach:
    - Use Checkout Session line_items API (not Session.retrieve expand)
    - Expand line item price
    - Read price.metadata.plan_slug
    """
    if not session_id:
        return ""

    try:
        li = stripe.checkout.Session.list_line_items(
            session_id,
            limit=10,
            expand=["data.price"],
        )

        data = (li or {}).get("data") or []
        logger.info(
            "PPA:plan_slug_line_items_listed session=%s line_items_count=%s",
            session_id,
            len(data),
        )

        for item in data:
            price = (item or {}).get("price") or {}
            md = (price or {}).get("metadata") or {}
            plan_slug = (md.get("plan_slug") or "").strip().lower()

            logger.info(
                "PPA:plan_slug_line_item session=%s price_id=%s plan_slug=%s price_md=%s",
                session_id,
                (price.get("id") or ""),
                plan_slug,
                md,
            )

            if plan_slug:
                return plan_slug

    except Exception as e:
        logger.exception("PPA:plan_slug_lookup_failed session=%s err=%s", session_id, str(e))

    return ""

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
    IMPORTANT: Do NOT force Solo -> Tyler.
    """
    s = (raw or "").strip().lower()
    if not s:
        return "tyler"
    if s in {"tyler", "early bird tyler", "tyler early bird", "earlybird", "early-bird"}:
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

    # CHANGED: Allow one endpoint to accept BOTH live + test/sandbox webhook signatures when both secrets exist.
    # We try secrets in a safe order:
    #   1) primary (based on PPA_STRIPE_MODE)
    #   2) the "other" mode secret (if set)
    #   3) STRIPE_WEBHOOK_SECRET legacy fallback (if set and not already tried)
    candidates = []  # CHANGED:
    seen = set()  # CHANGED:

    def _add_candidate(secret_val: str, source_name: str) -> None:  # CHANGED:
        if not secret_val:
            return
        if secret_val in seen:
            return
        candidates.append((secret_val, source_name))
        seen.add(secret_val)

    _add_candidate(endpoint_secret, secret_source)  # CHANGED:

    other = "STRIPE_TEST_WEBHOOK_SECRET" if mode == "live" else "STRIPE_LIVE_WEBHOOK_SECRET"  # CHANGED:
    _add_candidate(os.getenv(other, ""), other)  # CHANGED:
    _add_candidate(os.getenv("STRIPE_WEBHOOK_SECRET", ""), "STRIPE_WEBHOOK_SECRET")  # CHANGED:

    logger.info(
        "PPA:stripe_webhook mode=%s secret_sources_tried=%s",
        mode,
        ",".join([src for _, src in candidates]),
    )  # CHANGED:

    event = None  # CHANGED:
    used_source = ""  # CHANGED:

    for secret_val, source_name in candidates:  # CHANGED:
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret_val)  # CHANGED:
            used_source = source_name  # CHANGED:
            break  # CHANGED:
        except ValueError:
            logger.warning("PPA:stripe_webhook invalid_payload")
            return JsonResponse({"ok": False, "error": "invalid_payload", "ver": WEBHOOK_VER}, status=400)
        except stripe.error.SignatureVerificationError:
            continue

    if event is None:  # CHANGED:
        logger.warning(
            "PPA:stripe_webhook invalid_signature sources_tried=%s",
            ",".join([src for _, src in candidates]),
        )  # CHANGED:
        return JsonResponse({"ok": False, "error": "invalid_signature", "ver": WEBHOOK_VER}, status=400)

    logger.info("PPA:stripe_webhook signature_ok source=%s", used_source)  # CHANGED:

    event_id = (event or {}).get("id", "")
    event_type = (event or {}).get("type", "")

    if event_type != "checkout.session.completed":
        return JsonResponse({"ok": True, "ver": WEBHOOK_VER, "data": {"event": event_type, "handled": False}})

    session = ((event or {}).get("data") or {}).get("object") or {}
    session_id = session.get("id", "")
    payment_status = session.get("payment_status", "")
    customer_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email") or ""
    customer_name = (session.get("customer_details") or {}).get("name") or ""

    # CHANGED: Price metadata is the source of truth (plan_slug)
    # IMPORTANT: Use event.livemode to select the correct Stripe secret key for retrieval/expands.
    _set_stripe_api_key_for_event(event)

    plan_slug = _get_plan_slug_from_price(session_id)

    if plan_slug:
        tier = plan_slug
        plan_code = plan_slug
    else:
        # Fallback: legacy tier normalization
        md = session.get("metadata") or {}
        raw_tier = md.get("tier") or md.get("plan") or md.get("plan_code") or md.get("tier_name") or ""
        tier = _normalize_tier(raw_tier)
        plan_code = _derive_plan_code(tier)

    logger.info(
        "PPA:checkout_completed_resolved session_id=%s livemode=%s tier=%s plan_code=%s plan_slug=%s",
        session_id,
        bool((event or {}).get("livemode")),
        tier,
        plan_code,
        plan_slug,
    )

    # Persist Order + License FIRST (LOCKED ordering)
    Order = _model("postpress_ai", "Order")
    License = _model("postpress_ai", "License")

    order_created = False
    license_created = False

    # Persist minimal snapshots for audit/debug (not secrets)
    try:
        raw_event_safe = json.loads(payload.decode("utf-8"))
    except Exception:
        raw_event_safe = {"id": event_id, "type": event_type}

    try:
        raw_session_safe = json.loads(json.dumps(session))
    except Exception:
        raw_session_safe = {"id": session_id, "payment_status": payment_status}

    license_obj = None  # CHANGED: ensure exists after atomic block for later email section

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
                logger.exception("PPA:order_save_failed session=%s", session_id)

        # --- License upsert (idempotent by stripe_session_id) ---
        if _has_field(License, "stripe_session_id"):
            license_obj, created = License.objects.get_or_create(  # type: ignore
                stripe_session_id=session_id,
                defaults={},
            )
            license_created = bool(created)
        else:
            if _has_field(License, "order_id") and order is not None:
                license_obj, created = License.objects.get_or_create(  # type: ignore
                    order=order,
                    defaults={},
                )
                license_created = bool(created)
            else:
                license_obj = License.objects.order_by("-id").first()

        if license_obj is not None:
            _set_if_field(license_obj, "email", customer_email)
            _set_if_field(license_obj, "tier", tier)
            _set_if_field(license_obj, "plan_code", plan_code)

            Plan = _model("postpress_ai", "Plan")
            plan_obj = None
            try:
                if _has_field(Plan, "code"):
                    plan_obj = Plan.objects.filter(code=plan_code).first()
            except Exception:
                plan_obj = None

            max_sites = _derive_max_sites_from_plan(plan_obj, fallback=3 if plan_code == "tyler" else 1)
            _set_if_field(license_obj, "max_sites", max_sites)

            if payment_status == "paid":
                _set_if_field(license_obj, "status", "active")
                _set_if_field(license_obj, "is_active", True)

            if order is not None:
                _set_if_field(license_obj, "order", order)

            try:
                license_obj.save()
            except Exception:
                logger.exception("PPA:license_save_failed session=%s", session_id)

    # Command Center wiring happens AFTER Order + License (LOCKED ordering)
    customer_db_id = None
    plan_db_id = None
    subscription_db_id = None
    entitlement_db_id = None

    try:
        Customer = _model("postpress_ai", "Customer")
        Plan = _model("postpress_ai", "Plan")
        Subscription = _model("postpress_ai", "Subscription")
        Entitlement = _model("postpress_ai", "Entitlement")

        customer_obj = None
        if customer_email and _has_field(Customer, "email"):
            customer_obj, _ = Customer.objects.get_or_create(email=customer_email, defaults={})  # type: ignore
            customer_db_id = getattr(customer_obj, "id", None)
            _set_if_field(customer_obj, "name", customer_name)
            try:
                customer_obj.save()
            except Exception:
                pass

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

        if subscription_obj is not None and _has_field(Entitlement, "subscription"):
            entitlement_obj, _ = Entitlement.objects.get_or_create(subscription=subscription_obj, defaults={})  # type: ignore
            entitlement_db_id = getattr(entitlement_obj, "id", None)
            if plan_code == "tyler":
                _set_if_field(entitlement_obj, "max_sites", 3)
            try:
                entitlement_obj.save()
            except Exception:
                pass

    except Exception:
        logger.exception("PPA:command_center_wiring_failed session=%s", session_id)

    # If we don't have the minimum for email, still return OK (Stripe wants 2xx).
    if not customer_email or not event_id:
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
                    "license_emailed": False,
                    "email_skipped": True,
                    "email_reason": "missing_email_or_event_id",
                    "customer_db_id": customer_db_id,
                    "plan_db_id": plan_db_id,
                    "subscription_db_id": subscription_db_id,
                    "entitlement_db_id": entitlement_db_id,
                },
            }
        )

    # Email delivery (idempotent on Stripe retries)
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

    # Create EmailLog row first (winner sends)
    EmailLog = _model("postpress_ai", "EmailLog")
    elog = EmailLog()  # type: ignore

    # Link customer if possible
    try:
        if customer_db_id and _has_field(EmailLog, "customer_id"):
            _set_if_field(elog, "customer_id", customer_db_id)
    except Exception:
        pass

    _set_if_field(elog, "to_email", customer_email)
    _set_if_field(elog, "subject", "Welcome to PostPress AI — here’s your key")  # audit-only; emailing.py owns actual subject
    _set_if_field(elog, "email_type", getattr(EmailLog, "TYPE_LICENSE_KEY", "license_key"))
    _set_if_field(elog, "status", getattr(EmailLog, "STATUS_QUEUED", "queued"))
    _set_if_field(elog, "provider", "sendgrid")
    _set_if_field(elog, "created_at", timezone.now())

    # Safe meta (do NOT store full license keys)
    meta: Dict[str, Any] = {
        "stripe_event_id": event_id,
        "stripe_session_id": session_id,
        "plan_code": plan_code,
        "tier": tier,
        "payment_status": payment_status,
    }

    # Store masked key info for admin visibility
    license_key = ""
    max_sites = 3 if plan_code == "tyler" else 1
    if license_obj is not None:
        try:
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

    # Set the new column if it exists (post-migration), without assuming it exists.  # CHANGED:
    _set_if_field(elog, "stripe_event_id", event_id)  # CHANGED:

    try:
        elog.save()  # CHANGED:
    except IntegrityError:  # CHANGED:
        logger.info("PPA:email_log idempotent hit (IntegrityError) to=%s event=%s", customer_email, event_id)  # CHANGED:
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

    # Send email
    provider_msg_id = ""
    try:
        provider_msg_id = _send_license_key_email_best_effort(
            to_email=customer_email,
            customer_name=customer_name,
            license_key=license_key,
            tier=tier,
            max_sites=max_sites,
        )
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