
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
- 2026-02-27: FIX: Command Center wiring now supplies required Entitlement defaults (customer+plan)
             and always ensures active entitlements have a license_id for paid checkouts.
             Also fixes Order/Customer/Plan field mapping and blocks email unless paid.  # CHANGED:
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

WEBHOOK_VER = "stripe-webhook.v2026-02-27.1"  # CHANGED:


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


def _split_name(full_name: str) -> Tuple[str, str]:  # CHANGED:
    """Best-effort split of a full name into (first, last)."""
    s = (full_name or "").strip()
    if not s:
        return "", ""
    parts = [p for p in s.split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _plan_code_to_license_slug(plan_code: str) -> str:  # CHANGED:
    """Map Plan.code -> License.plan_slug (keeps Agency BYO normalization)."""
    code = (plan_code or "").strip().lower()
    if not code:
        return "tyler"
    if code == "agency_unlimited_byo":
        return "agency_byo"
    if code == "solo":  # legacy alias
        return "tyler"
    return code


def _default_plan_seed(plan_code: str) -> Dict[str, Any]:  # CHANGED:
    """Fallback plan defaults when Plan row doesn't exist yet."""
    code = (plan_code or "").strip().lower()
    # Mirror seed_default_plans() + keep Tyler behavior.
    if code == "tyler":
        return {"name": "Tyler", "max_sites": 3, "ai_mode": "included", "is_active": True}
    if code == "solo":
        return {"name": "Solo", "max_sites": 1, "ai_mode": "included", "is_active": True}
    if code == "creator":
        return {"name": "Creator", "max_sites": 3, "ai_mode": "included", "is_active": True}
    if code == "studio":
        return {"name": "Studio", "max_sites": 10, "ai_mode": "included", "is_active": True}
    if code == "agency":
        return {"name": "Agency (AI Included)", "max_sites": 25, "ai_mode": "included", "is_active": True}
    if code in {"agency_unlimited_byo", "agency_byo"}:
        return {"name": "Agency Unlimited (BYO Key)", "max_sites": None, "ai_mode": "byo_key", "is_active": True}
    return {"name": code.title() if code else "Plan", "max_sites": 1, "ai_mode": "included", "is_active": True}


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
    - Order: enforced by unique Stripe session id.
    - Entitlement + License: ensured by (subscription -> entitlement -> license) linking.
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
        logger.warning("PPA:stripe_webhook invalid_signature sources_tried=%s", ",".join([src for _, src in candidates]))  # CHANGED:
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

    # Stripe identifiers (safe to store; never secrets)
    stripe_customer_id = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    stripe_payment_intent_id = session.get("payment_intent") or ""
    amount_total = session.get("amount_total")
    currency = session.get("currency")

    is_paid = payment_status == "paid"

    # Metadata-driven tier, with locked fallback behavior
    md = session.get("metadata") or {}
    raw_tier = md.get("tier") or md.get("plan") or md.get("plan_code") or md.get("tier_name") or ""
    tier = _normalize_tier(raw_tier)
    plan_code = _derive_plan_code(tier)

    # Persist Order FIRST (idempotent by stripe_session_id)  # CHANGED:
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

    license_obj = None  # CHANGED: may be created here (if schema supports), or later during Command Center wiring

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
            _set_if_field(order, "stripe_event_id", event_id)
            _set_if_field(order, "stripe_customer_id", stripe_customer_id)
            _set_if_field(order, "stripe_payment_intent_id", stripe_payment_intent_id)
            _set_if_field(order, "purchaser_email", customer_email)
            _set_if_field(order, "purchaser_name", customer_name)
            _set_if_field(order, "amount_total", amount_total)
            _set_if_field(order, "currency", currency)
            _set_if_field(order, "status", "fulfilled" if is_paid else "pending")
            _set_if_field(order, "raw_event", raw_event_safe)
            _set_if_field(order, "raw_session", raw_session_safe)
            try:
                order.save()
            except Exception:
                logger.exception("PPA:order_save_failed session=%s", session_id)

        # --- Optional License upsert (only when schema supports stripe_session_id + required fields) ---
        # If your License model does NOT have stripe_session_id, license creation is handled later via Entitlement.  # CHANGED:
        if (
            _has_field(License, "stripe_session_id")
            and _has_field(License, "key")
            and _has_field(License, "plan_slug")
        ):
            try:
                from postpress_ai.license_keys import generate_unique_license_key  # lazy
            except Exception:
                generate_unique_license_key = None  # type: ignore

            if generate_unique_license_key:
                Plan = _model("postpress_ai", "Plan")
                plan_obj = None
                try:
                    if _has_field(Plan, "code"):
                        plan_obj = Plan.objects.filter(code=plan_code).first()
                except Exception:
                    plan_obj = None

                max_sites = _derive_max_sites_from_plan(plan_obj, fallback=3 if plan_code == "tyler" else 1)
                unlimited = getattr(plan_obj, "max_sites", None) is None if plan_obj is not None else (plan_code == "agency_unlimited_byo")
                if unlimited:
                    max_sites = None

                ai_mode = getattr(plan_obj, "ai_mode", "included") if plan_obj is not None else ("byo_key" if plan_code == "agency_unlimited_byo" else "included")
                byo_required = (ai_mode == "byo_key")
                ai_included = not byo_required

                plan_slug = _plan_code_to_license_slug(plan_code)

                def _exists(k: str) -> bool:
                    try:
                        return License.objects.filter(key=k).exists()
                    except Exception:
                        return False

                defaults = {
                    "key": generate_unique_license_key(exists=_exists),
                    "plan_slug": plan_slug,
                    "status": "active" if is_paid else "paused",
                    "max_sites": max_sites,
                    "unlimited_sites": bool(unlimited),
                    "byo_key_required": bool(byo_required),
                    "ai_included": bool(ai_included),
                }

                try:
                    license_obj, created = License.objects.get_or_create(  # type: ignore
                        stripe_session_id=session_id,
                        defaults=defaults,
                    )
                    license_created = bool(created)

                    # Keep it fresh (schema drift safe)
                    _set_if_field(license_obj, "plan_slug", plan_slug)
                    _set_if_field(license_obj, "status", "active" if is_paid else "paused")
                    _set_if_field(license_obj, "max_sites", max_sites)
                    _set_if_field(license_obj, "unlimited_sites", bool(unlimited))
                    _set_if_field(license_obj, "byo_key_required", bool(byo_required))
                    _set_if_field(license_obj, "ai_included", bool(ai_included))
                    try:
                        license_obj.save()
                    except Exception:
                        logger.exception("PPA:license_save_failed session=%s", session_id)
                except Exception:
                    logger.exception("PPA:license_upsert_failed session=%s", session_id)

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
        License = _model("postpress_ai", "License")

        with transaction.atomic():  # CHANGED: keep linking consistent
            # --- Customer ---
            customer_obj = None
            if customer_email and _has_field(Customer, "email"):
                customer_obj, _ = Customer.objects.get_or_create(email=customer_email, defaults={})  # type: ignore
                customer_db_id = getattr(customer_obj, "id", None)

                first, last = _split_name(customer_name)
                if first:
                    _set_if_field(customer_obj, "first_name", first)
                if last:
                    _set_if_field(customer_obj, "last_name", last)
                _set_if_field(customer_obj, "last_seen_at", timezone.now())

                try:
                    customer_obj.save()
                except Exception:
                    pass

            # --- Plan ---
            plan_obj = None
            if _has_field(Plan, "code"):
                defaults = _default_plan_seed(plan_code)
                try:
                    plan_obj, created = Plan.objects.get_or_create(code=plan_code, defaults=defaults)  # type: ignore
                    plan_db_id = getattr(plan_obj, "id", None)

                    # Keep plan fields sensible even if seeded elsewhere
                    _set_if_field(plan_obj, "name", getattr(plan_obj, "name", "") or defaults.get("name"))
                    if plan_code == "tyler":
                        _set_if_field(plan_obj, "max_sites", 3)
                        _set_if_field(plan_obj, "ai_mode", "included")
                    if plan_code == "agency_unlimited_byo":
                        _set_if_field(plan_obj, "max_sites", None)
                        _set_if_field(plan_obj, "ai_mode", "byo_key")
                    _set_if_field(plan_obj, "is_active", True)

                    try:
                        plan_obj.save()
                    except Exception:
                        pass
                except Exception:
                    plan_obj = None

            # --- Subscription ---
            subscription_obj = None
            if customer_obj is not None and plan_obj is not None:
                if _has_field(Subscription, "customer") and _has_field(Subscription, "plan"):
                    subscription_obj, _ = Subscription.objects.get_or_create(  # type: ignore
                        customer=customer_obj,
                        plan=plan_obj,
                        defaults={},
                    )
                    subscription_db_id = getattr(subscription_obj, "id", None)

                    # status: be conservative for unpaid sessions
                    if is_paid:
                        _set_if_field(subscription_obj, "status", getattr(subscription_obj, "STATUS_ACTIVE", "active"))
                    else:
                        _set_if_field(subscription_obj, "status", getattr(subscription_obj, "STATUS_INCOMPLETE", "incomplete"))

                    _set_if_field(subscription_obj, "stripe_customer_id", stripe_customer_id)
                    _set_if_field(subscription_obj, "stripe_subscription_id", stripe_subscription_id)
                    _set_if_field(subscription_obj, "stripe_payment_intent_id", stripe_payment_intent_id)
                    _set_if_field(subscription_obj, "stripe_checkout_session_id", session_id)

                    try:
                        subscription_obj.save()
                    except Exception:
                        pass

            # --- Entitlement (REQUIRED: customer + plan) ---
            entitlement_obj = None
            if customer_obj is not None and plan_obj is not None:
                ent_defaults: Dict[str, Any] = {
                    "customer": customer_obj,
                    "plan": plan_obj,
                    "status": "active" if is_paid else "paused",
                }

                try:
                    if subscription_obj is not None and _has_field(Entitlement, "subscription"):
                        entitlement_obj, _ = Entitlement.objects.get_or_create(  # type: ignore
                            subscription=subscription_obj,
                            defaults=ent_defaults,
                        )
                    else:
                        entitlement_obj, _ = Entitlement.objects.get_or_create(  # type: ignore
                            customer=customer_obj,
                            plan=plan_obj,
                            defaults={"status": "active" if is_paid else "paused"},
                        )
                except IntegrityError:
                    # If a concurrent delivery created it, fetch the newest match.
                    if subscription_obj is not None and _has_field(Entitlement, "subscription"):
                        entitlement_obj = Entitlement.objects.filter(subscription=subscription_obj).order_by("-id").first()
                    else:
                        entitlement_obj = Entitlement.objects.filter(customer=customer_obj, plan=plan_obj).order_by("-id").first()

                if entitlement_obj is not None:
                    entitlement_db_id = getattr(entitlement_obj, "id", None)
                    # Keep links correct (defensive)
                    _set_if_field(entitlement_obj, "customer", customer_obj)
                    _set_if_field(entitlement_obj, "plan", plan_obj)
                    if subscription_obj is not None:
                        _set_if_field(entitlement_obj, "subscription", subscription_obj)
                    _set_if_field(entitlement_obj, "status", "active" if is_paid else "paused")

                    # Attach/ensure License for paid sessions
                    if is_paid and _has_field(Entitlement, "license"):
                        needs_license = getattr(entitlement_obj, "license_id", None) in (None, "")
                        if needs_license:
                            # Prefer license created earlier (when schema supports stripe_session_id)
                            lic = license_obj

                            if lic is None:
                                # Create a fresh license (idempotent per entitlement: only if missing)
                                try:
                                    from postpress_ai.license_keys import generate_unique_license_key
                                except Exception:
                                    generate_unique_license_key = None  # type: ignore

                                if generate_unique_license_key:
                                    plan_slug = _plan_code_to_license_slug(plan_code)
                                    plan_max = getattr(plan_obj, "max_sites", None)
                                    unlimited = (plan_max is None) or (isinstance(plan_max, int) and plan_max <= 0)
                                    max_sites = None if unlimited else int(plan_max)

                                    ai_mode = getattr(plan_obj, "ai_mode", "included")
                                    byo_required = (ai_mode == "byo_key") or (plan_slug == "agency_byo")
                                    ai_included = not byo_required

                                    key = generate_unique_license_key(
                                        exists=lambda k: License.objects.filter(key=k).exists()
                                    )

                                    create_kwargs: Dict[str, Any] = {}
                                    _set = lambda n, v: create_kwargs.__setitem__(n, v)

                                    if _has_field(License, "key"):
                                        _set("key", key)
                                    if _has_field(License, "plan_slug"):
                                        _set("plan_slug", plan_slug)
                                    if _has_field(License, "status"):
                                        _set("status", "active")
                                    if _has_field(License, "max_sites"):
                                        _set("max_sites", max_sites)
                                    if _has_field(License, "unlimited_sites"):
                                        _set("unlimited_sites", bool(unlimited))
                                    if _has_field(License, "byo_key_required"):
                                        _set("byo_key_required", bool(byo_required))
                                    if _has_field(License, "ai_included"):
                                        _set("ai_included", bool(ai_included))

                                    lic = License.objects.create(**create_kwargs)
                                    license_created = True

                            if lic is not None:
                                _set_if_field(entitlement_obj, "license", lic)
                                license_obj = lic  # CHANGED: used for email below

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

    # CHANGED: Only email keys after successful payment.
    if not is_paid:
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
                    "email_reason": "payment_not_paid",
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


    if not license_key:  # CHANGED:
        logger.warning("PPA:missing_license_key session=%s entitlement=%s", session_id, entitlement_db_id)  # CHANGED:
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
                    "email_reason": "missing_license_key",
                    "customer_db_id": customer_db_id,
                    "plan_db_id": plan_db_id,
                    "subscription_db_id": subscription_db_id,
                    "entitlement_db_id": entitlement_db_id,
                },
            }
        )

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
                "order_status": "fulfilled" if is_paid else "pending",
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
