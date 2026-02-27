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
- PPA_STRIPE_MODE: "live" | "test"  (default: live)
- STRIPE_LIVE_WEBHOOK_SECRET (preferred when mode=live)
- STRIPE_TEST_WEBHOOK_SECRET (preferred when mode=test)
- STRIPE_WEBHOOK_SECRET (fallback for legacy deployments)

SECRET KEY SELECTION (LOCKED BEHAVIOR)
- Stripe object retrieval MUST use the secret key that matches event.livemode:
    - livemode=True  -> STRIPE_LIVE_SECRET_KEY
    - livemode=False -> STRIPE_SECRET_KEY
- IMPORTANT: Do NOT cross-fallback between live/test keys.
  If the correct key is missing, raise ImproperlyConfigured.

PLAN RESOLUTION ORDER (LOCKED)
1) price.metadata.plan_slug
2) fallback to legacy tier normalization (_normalize_tier)
3) never default to "tyler" unless truly Tyler

CHANGE LOG
- 2026-02-26: FIX: Allow one endpoint to accept BOTH live + test/sandbox webhook signatures
             by trying multiple secrets in a safe order (env var names only; never log secrets).
- 2026-02-26: FIX: Plan slug resolution uses Checkout Session line_items + Price metadata.plan_slug
- 2026-02-26: FIX: Stripe secret key selection is STRICTLY based on event.livemode
- 2026-02-26: FIX: Entitlement get_or_create includes required NOT NULL FKs (customer/plan) when present
- 2026-02-27: FIX: License issuance when License model lacks stripe_session_id/order FK:
             - Issue License via generated unique key + plan_slug
             - Idempotency via Order.notes PPA_LICENSE_KEY
             - Email retry allowed when EmailLog exists but status=failed
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

import stripe
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

WEBHOOK_VER = "stripe-webhook.v2026-02-26.5"  # CHANGED:


# ---------------------------
# Helpers (locked behavior)
# ---------------------------


def _get_stripe_webhook_secret_info() -> Tuple[str, str, str]:
    """
    Returns: (secret, source_env_var_name, mode)

    Required behavior:
    - Uses PPA_STRIPE_MODE in {"live","test"} (default: live)
    - Picks STRIPE_LIVE_WEBHOOK_SECRET or STRIPE_TEST_WEBHOOK_SECRET
    - Fallback to STRIPE_WEBHOOK_SECRET
    - NEVER logs the secret value
    """
    mode = (os.getenv("PPA_STRIPE_MODE") or "live").strip().lower()
    if mode not in ("live", "test"):
        mode = "live"

    primary = "STRIPE_LIVE_WEBHOOK_SECRET" if mode == "live" else "STRIPE_TEST_WEBHOOK_SECRET"
    secret = os.getenv(primary) or ""
    source = primary

    if not secret:
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "") or ""
        source = "STRIPE_WEBHOOK_SECRET"

    if not secret:
        raise ImproperlyConfigured(
            f"Missing Stripe webhook secret. Set {primary} (preferred) or STRIPE_WEBHOOK_SECRET."
        )

    return secret, source, mode


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 6:
        return "PPA-…"
    return f"{key[:4]}-…{key[-4:]}"


def _set_stripe_api_key_for_event(event: dict) -> Tuple[str, str]:
    """
    Choose Stripe secret key STRICTLY based on webhook event livemode.

    LOCKED:
    - livemode=True  -> STRIPE_LIVE_SECRET_KEY (required)
    - livemode=False -> STRIPE_SECRET_KEY (required)

    IMPORTANT:
    - Do NOT cross-fallback between live/test keys.
      If the correct key is missing, raise ImproperlyConfigured.
    """
    is_live = bool((event or {}).get("livemode"))
    primary = "STRIPE_LIVE_SECRET_KEY" if is_live else "STRIPE_SECRET_KEY"
    key = (os.getenv(primary) or "").strip()

    if not key:
        raise ImproperlyConfigured(f"Missing Stripe secret key for livemode={is_live}. Set {primary}.")

    stripe.api_key = key
    logger.info("PPA:stripe api_key_set livemode=%s source=%s key=%s", is_live, primary, _mask_key(key))
    return key, primary


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

    IMPORTANT (LOCKED):
    - Do NOT force Solo -> Tyler.
    - Do NOT default to 'tyler' when blank.
    """
    s = (raw or "").strip().lower()
    if not s:
        return ""
    if s in {"tyler", "early bird tyler", "tyler early bird", "earlybird", "early-bird"}:
        return "tyler"
    return s


def _derive_plan_code(tier: str) -> str:
    """
    LOCKED: Plan code derivation.

    IMPORTANT (LOCKED):
    - Do NOT default to 'tyler' unless tier normalizes to Tyler.
    - If tier is missing/unknown, use 'unknown' (safe sentinel) rather than forcing Tyler.
    """
    t = _normalize_tier(tier)
    return t or "unknown"


def _derive_max_sites_from_plan(plan_obj: Any, fallback: int) -> int:
    """Read plan.max_sites if present; else fallback."""
    if plan_obj is None:
        return fallback
    if hasattr(plan_obj, "max_sites") and getattr(plan_obj, "max_sites") is not None:
        try:
            return int(getattr(plan_obj, "max_sites"))
        except Exception:
            return fallback
    return fallback


def _normalize_price_metadata(md: Dict[str, Any]) -> Dict[str, str]:
    """Normalize Stripe Price metadata keys by stripping whitespace and lowercasing."""
    out: Dict[str, str] = {}
    for k, v in (md or {}).items():
        kk = str(k).strip().lower().replace("-", "_")
        out[kk] = str(v).strip() if v is not None else ""
    return out


def _get_plan_slug_and_price_md(session_id: str) -> Tuple[str, Dict[str, str]]:
    """
    Source of truth: Stripe Price metadata.plan_slug

    Reliable approach:
    - Use Checkout Session line_items API
    - Expand line item price
    - Read price.metadata.plan_slug

    NOTE: Stripe dashboard metadata keys may include trailing spaces, so we normalize keys.
    """
    if not session_id:
        return "", {}

    try:
        li = stripe.checkout.Session.list_line_items(session_id, limit=10, expand=["data.price"])
        data = (li or {}).get("data") or []
        logger.info("PPA:plan_slug_line_items_listed session=%s line_items_count=%s", session_id, len(data))

        for item in data:
            price = (item or {}).get("price") or {}
            md_raw = (price or {}).get("metadata") or {}
            md = _normalize_price_metadata(md_raw)

            plan_slug = (md.get("plan_slug") or "").strip().lower()
            logger.info(
                "PPA:plan_slug_line_item session=%s price_id=%s plan_slug=%s price_md=%s",
                session_id,
                (price.get("id") or ""),
                plan_slug,
                md_raw,
            )
            return plan_slug, md

    except Exception as e:
        logger.exception("PPA:plan_slug_lookup_failed session=%s err=%s", session_id, str(e))

    return "", {}


def _order_notes_get_license_key(notes: str) -> str:
    if not notes:
        return ""
    m = re.search(r"PPA_LICENSE_KEY=([A-Z0-9-]+)", notes or "")
    return (m.group(1) if m else "") or ""


def _order_notes_set_license_key(notes: str, key: str) -> str:
    notes = notes or ""
    if re.search(r"PPA_LICENSE_KEY=[A-Z0-9-]+", notes):
        return re.sub(r"PPA_LICENSE_KEY=[A-Z0-9-]+", f"PPA_LICENSE_KEY={key}", notes)
    sep = chr(10) if notes and not notes.endswith(chr(10)) else ""
    return f"{notes}{sep}PPA_LICENSE_KEY={key}"


def _license_defaults_for_plan(plan_slug: str, price_md: Dict[str, str]) -> Dict[str, Any]:
    """
    Compute License flags/limits from plan_slug and (optional) price metadata.

    - site_limit (int) overrides max_sites when present.
    - byo_key (truthy) forces byo_key_required True and ai_included False.
    """
    slug = (plan_slug or "").strip().lower().replace("-", "_")

    def _to_int(s: str) -> Optional[int]:
        try:
            ss = (s or "").strip()
            if not ss:
                return None
            return int(float(ss))
        except Exception:
            return None

    site_limit = _to_int(price_md.get("site_limit", ""))
    byo_raw = (price_md.get("byo_key", "") or "").strip().lower()
    byo = byo_raw in {"1", "true", "yes", "on"}

    defaults = {
        "tyler": {"max_sites": 3, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
        "solo": {"max_sites": 1, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
        "creator": {"max_sites": 3, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
        "studio": {"max_sites": 10, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
        "agency": {"max_sites": 25, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
        "agency_byo": {"max_sites": None, "unlimited_sites": True, "byo_key_required": True, "ai_included": False},
        "agency_unlimited_byo": {"max_sites": None, "unlimited_sites": True, "byo_key_required": True, "ai_included": False},
    }
    base = defaults.get(
        slug,
        {"max_sites": 1, "unlimited_sites": False, "byo_key_required": False, "ai_included": True},
    )

    unlimited_sites = bool(base.get("unlimited_sites"))
    max_sites = base.get("max_sites")

    if site_limit is not None:
        if site_limit <= 0:
            unlimited_sites = True
            max_sites = None
        else:
            unlimited_sites = False
            max_sites = int(site_limit)

    byo_key_required = bool(byo or base.get("byo_key_required"))
    ai_included = bool((not byo_key_required) and base.get("ai_included"))

    return {
        "max_sites": max_sites,
        "unlimited_sites": unlimited_sites,
        "byo_key_required": byo_key_required,
        "ai_included": ai_included,
    }


def _email_log_lookup_locked(to_email: str, stripe_event_id: str):
    """
    DB-level idempotency lookup.

    - If EmailLog has stripe_event_id column: query (fast)
    - Else: fallback scan meta['stripe_event_id'] in Python (pre-migration safe)

    Returns EmailLog instance or None.
    """
    if not to_email or not stripe_event_id:
        return None

    EmailLog = _model("postpress_ai", "EmailLog")

    try:
        EmailLog._meta.get_field("stripe_event_id")
        has_col = True
    except Exception:
        has_col = False

    if has_col:
        return EmailLog.objects.filter(to_email=to_email, stripe_event_id=stripe_event_id).order_by("-id").first()

    qs = EmailLog.objects.filter(to_email=to_email).only("id", "meta").order_by("-id")[:250]
    for row in qs:
        ev = (row.meta or {}).get("stripe_event_id")
        if ev == stripe_event_id:
            return row
    return None


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
    from postpress_ai.emailing import send_license_key_email

    try:
        send_license_key_email(
            to_email=to_email,
            name=customer_name,
            license_key=license_key,
            tier=tier,
            max_sites=max_sites,
        )
        return ""
    except TypeError:
        pass

    try:
        send_license_key_email(
            to_email,
            license_key,
            tier=tier,
            max_sites=max_sites,
            name=customer_name,
        )
        return ""
    except TypeError:
        pass

    send_license_key_email(to_email=to_email, license_key=license_key)
    return ""


# ---------------------------
# Main webhook
# ---------------------------


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    """
    Stripe webhook receiver with signature verification.
    Handles: checkout.session.completed
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed", "ver": WEBHOOK_VER}, status=405)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    endpoint_secret, secret_source, mode = _get_stripe_webhook_secret_info()

    # Allow one endpoint to accept BOTH live + test/sandbox webhook signatures when both secrets exist.
    candidates = []
    seen = set()

    def _add_candidate(secret_val: str, source_name: str) -> None:
        if not secret_val:
            return
        if secret_val in seen:
            return
        candidates.append((secret_val, source_name))
        seen.add(secret_val)

    _add_candidate(endpoint_secret, secret_source)
    other = "STRIPE_TEST_WEBHOOK_SECRET" if mode == "live" else "STRIPE_LIVE_WEBHOOK_SECRET"
    _add_candidate(os.getenv(other, ""), other)
    _add_candidate(os.getenv("STRIPE_WEBHOOK_SECRET", ""), "STRIPE_WEBHOOK_SECRET")

    logger.info(
        "PPA:stripe_webhook mode=%s secret_sources_tried=%s",
        mode,
        ",".join([src for _, src in candidates]),
    )

    event = None
    used_source = ""

    for secret_val, source_name in candidates:
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=secret_val)
            used_source = source_name
            break
        except ValueError:
            logger.warning("PPA:stripe_webhook invalid_payload")
            return JsonResponse({"ok": False, "error": "invalid_payload", "ver": WEBHOOK_VER}, status=400)
        except stripe.error.SignatureVerificationError:
            continue

    if event is None:
        logger.warning(
            "PPA:stripe_webhook invalid_signature sources_tried=%s",
            ",".join([src for _, src in candidates]),
        )
        return JsonResponse({"ok": False, "error": "invalid_signature", "ver": WEBHOOK_VER}, status=400)

    logger.info("PPA:stripe_webhook signature_ok source=%s", used_source)

    event_id = (event or {}).get("id", "")
    event_type = (event or {}).get("type", "")

    if event_type != "checkout.session.completed":
        return JsonResponse({"ok": True, "ver": WEBHOOK_VER, "data": {"event": event_type, "handled": False}})

    session = ((event or {}).get("data") or {}).get("object") or {}
    session_id = session.get("id", "")
    payment_status = session.get("payment_status", "")
    customer_email = (session.get("customer_details") or {}).get("email") or session.get("customer_email") or ""
    customer_name = (session.get("customer_details") or {}).get("name") or ""

    # Price metadata is the source of truth (plan_slug)
    # IMPORTANT: Use event.livemode to select the correct Stripe secret key for retrieval/expands.
    _set_stripe_api_key_for_event(event)

    plan_slug, price_md = _get_plan_slug_and_price_md(session_id)

    if plan_slug:
        tier = plan_slug
        plan_code = plan_slug
    else:
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

    Order = _model("postpress_ai", "Order")
    License = _model("postpress_ai", "License")

    order_created = False
    license_created = False

    try:
        raw_event_safe = json.loads(payload.decode("utf-8"))
    except Exception:
        raw_event_safe = {"id": event_id, "type": event_type}

    try:
        raw_session_safe = json.loads(json.dumps(session))
    except Exception:
        raw_session_safe = {"id": session_id, "payment_status": payment_status}

    license_obj = None

    with transaction.atomic():
        order, created = Order.objects.get_or_create(stripe_session_id=session_id, defaults={})  # type: ignore
        order_created = bool(created)

        try:
            order = Order.objects.select_for_update().get(pk=order.pk)  # type: ignore
        except Exception:
            pass

        _set_if_field(order, "stripe_event_id", event_id)
        _set_if_field(order, "purchaser_email", customer_email)
        _set_if_field(order, "purchaser_name", customer_name)
        _set_if_field(order, "stripe_customer_id", session.get("customer") or "")
        _set_if_field(order, "stripe_payment_intent_id", session.get("payment_intent") or "")
        _set_if_field(order, "amount_total", session.get("amount_total"))
        _set_if_field(order, "currency", session.get("currency"))
        _set_if_field(order, "status", "fulfilled" if payment_status == "paid" else "pending")
        _set_if_field(order, "raw_event", raw_event_safe)
        _set_if_field(order, "raw_session", raw_session_safe)
        try:
            order.save()
        except Exception:
            logger.exception("PPA:order_save_failed session=%s", session_id)

        existing_key = ""
        if _has_field(Order, "notes"):
            existing_key = _order_notes_get_license_key(str(getattr(order, "notes", "") or ""))

        if existing_key:
            try:
                license_obj = License.objects.filter(key=existing_key).first()
            except Exception:
                license_obj = None

        if license_obj is None:
            from postpress_ai.license_keys import generate_unique_license_key

            def _exists(k: str) -> bool:
                return License.objects.filter(key=k).exists()

            new_key = generate_unique_license_key(exists=_exists)

            plan_for_license = (plan_slug or plan_code or tier or "").strip().lower().replace("-", "_")
            if not plan_for_license:
                plan_for_license = "unknown"

            defaults = _license_defaults_for_plan(plan_for_license, price_md)

            create_kwargs: Dict[str, Any] = {
                "key": new_key,
                "plan_slug": plan_for_license,
            }

            if _has_field(License, "status"):
                create_kwargs["status"] = "active" if payment_status == "paid" else "active"
            if _has_field(License, "max_sites"):
                create_kwargs["max_sites"] = defaults.get("max_sites")
            if _has_field(License, "unlimited_sites"):
                create_kwargs["unlimited_sites"] = defaults.get("unlimited_sites")
            if _has_field(License, "byo_key_required"):
                create_kwargs["byo_key_required"] = defaults.get("byo_key_required")
            if _has_field(License, "ai_included"):
                create_kwargs["ai_included"] = defaults.get("ai_included")

            try:
                license_obj = License.objects.create(**create_kwargs)  # type: ignore
                license_created = True
            except Exception:
                logger.exception("PPA:license_create_failed session=%s", session_id)
                license_obj = None

            if license_obj is not None and _has_field(Order, "notes"):
                try:
                    cur_notes = str(getattr(order, "notes", "") or "")
                    new_notes = _order_notes_set_license_key(cur_notes, str(getattr(license_obj, "key", "")))
                    _set_if_field(order, "notes", new_notes)
                    order.save(update_fields=["notes"])
                except Exception:
                    logger.exception("PPA:order_notes_save_failed session=%s", session_id)

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
        if plan_code and plan_code != "unknown" and _has_field(Plan, "code"):
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
            entitlement_defaults: Dict[str, Any] = {}

            if customer_obj is not None and _has_field(Entitlement, "customer"):
                entitlement_defaults["customer"] = customer_obj
            if plan_obj is not None and _has_field(Entitlement, "plan"):
                entitlement_defaults["plan"] = plan_obj

            entitlement_obj, created = Entitlement.objects.get_or_create(  # type: ignore
                subscription=subscription_obj,
                defaults=entitlement_defaults,
            )
            entitlement_db_id = getattr(entitlement_obj, "id", None)

            if not created:
                dirty_fields = []
                if customer_obj is not None and _has_field(Entitlement, "customer") and getattr(entitlement_obj, "customer_id", None) is None:
                    _set_if_field(entitlement_obj, "customer", customer_obj)
                    dirty_fields.append("customer")
                if plan_obj is not None and _has_field(Entitlement, "plan") and getattr(entitlement_obj, "plan_id", None) is None:
                    _set_if_field(entitlement_obj, "plan", plan_obj)
                    dirty_fields.append("plan")
                try:
                    if dirty_fields:
                        entitlement_obj.save(update_fields=dirty_fields)
                except Exception:
                    pass

            # Link Entitlement -> License once ("key for life" foundation)
            try:
                if (
                    entitlement_obj is not None
                    and 'license_obj' in locals()
                    and license_obj is not None
                    and _has_field(Entitlement, "license")
                    and getattr(entitlement_obj, "license_id", None) is None
                ):
                    entitlement_obj.license = license_obj
                    update_fields = ["license"]
                    if _has_field(Entitlement, "updated_at"):
                        update_fields.append("updated_at")
                    entitlement_obj.save(update_fields=update_fields)
            except Exception:
                logger.exception("PPA:entitlement_license_link_failed session=%s entitlement_id=%s", session_id, getattr(entitlement_obj, "id", None))

            # Ensure only one ACTIVE entitlement per customer (newest paid wins)
            try:
                if (
                    payment_status == "paid"
                    and entitlement_obj is not None
                    and customer_obj is not None
                    and _has_field(Entitlement, "customer")
                    and _has_field(Entitlement, "status")
                ):
                    # Pick safe ACTIVE/INACTIVE values based on model choices if present
                    status_field = Entitlement._meta.get_field("status")
                    choices = [c[0] for c in (getattr(status_field, "choices", None) or [])]
                    choices_set = set(choices)

                    ACTIVE = "active" if ("active" in choices_set or not choices) else choices[0]
                    INACTIVE = (
                        "inactive" if "inactive" in choices_set else
                        "canceled" if "canceled" in choices_set else
                        "cancelled" if "cancelled" in choices_set else
                        "revoked" if "revoked" in choices_set else
                        "expired" if "expired" in choices_set else
                        "inactive"  # final fallback (DB can store even if not in choices)
                    )

                    # Deactivate all other entitlements for this customer
                    Entitlement.objects.filter(customer=customer_obj).exclude(id=entitlement_obj.id).update(status=INACTIVE)

                    # Make sure the current one is ACTIVE
                    if getattr(entitlement_obj, "status", None) != ACTIVE:
                        entitlement_obj.status = ACTIVE
                        update_fields = ["status"]
                        if _has_field(Entitlement, "updated_at"):
                            update_fields.append("updated_at")
                        entitlement_obj.save(update_fields=update_fields)
            except Exception:
                logger.exception("PPA:entitlement_single_active_enforce_failed session=%s customer_id=%s", session_id, getattr(customer_obj, "id", None))

            if plan_code == "tyler":
                _set_if_field(entitlement_obj, "max_sites_override", 3)
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

    EmailLog = _model("postpress_ai", "EmailLog")

    # Resolve license key for email
    license_key = ""
    max_sites_for_email = 3 if plan_code == "tyler" else 1
    if license_obj is not None:
        try:
            if hasattr(license_obj, "key"):
                license_key = str(getattr(license_obj, "key") or "")
            if hasattr(license_obj, "max_sites") and getattr(license_obj, "max_sites") is not None:
                try:
                    max_sites_for_email = int(getattr(license_obj, "max_sites"))
                except Exception:
                    pass
        except Exception:
            pass

    existing_elog = _email_log_lookup_locked(to_email=customer_email, stripe_event_id=event_id)

    # If already SENT, do not send again.
    if existing_elog is not None and getattr(existing_elog, "status", "") == getattr(EmailLog, "STATUS_SENT", "sent"):
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
                    "email_reason": "EmailLog exists (sent)",
                    "customer_db_id": customer_db_id,
                    "plan_db_id": plan_db_id,
                    "subscription_db_id": subscription_db_id,
                    "entitlement_db_id": entitlement_db_id,
                },
            }
        )

    # If exists but FAILED, allow retry using the same row (prevents duplicates).
    elog = existing_elog if existing_elog is not None else EmailLog()  # type: ignore

    if existing_elog is not None and getattr(existing_elog, "status", "") == getattr(EmailLog, "STATUS_FAILED", "failed"):
        try:
            _set_if_field(elog, "status", getattr(EmailLog, "STATUS_QUEUED", "queued"))
            _set_if_field(elog, "error_message", "")
        except Exception:
            pass

    if existing_elog is None:
        try:
            if customer_db_id and _has_field(EmailLog, "customer_id"):
                _set_if_field(elog, "customer_id", customer_db_id)
        except Exception:
            pass

        _set_if_field(elog, "to_email", customer_email)
        _set_if_field(elog, "subject", "Welcome to PostPress AI — here’s your key")
        _set_if_field(elog, "email_type", getattr(EmailLog, "TYPE_LICENSE_KEY", "license_key"))
        _set_if_field(elog, "status", getattr(EmailLog, "STATUS_QUEUED", "queued"))
        _set_if_field(elog, "provider", "sendgrid")
        _set_if_field(elog, "created_at", timezone.now())
        _set_if_field(elog, "stripe_event_id", event_id)

    meta: Dict[str, Any] = {
        "stripe_event_id": event_id,
        "stripe_session_id": session_id,
        "plan_code": plan_code,
        "tier": tier,
        "payment_status": payment_status,
        "license_key_masked": _mask_key(license_key),
        "max_sites": max_sites_for_email,
    }
    _set_if_field(elog, "meta", meta)

    try:
        elog.save()
    except IntegrityError:
        logger.info("PPA:email_log idempotent hit (IntegrityError) to=%s event=%s", customer_email, event_id)
        elog = _email_log_lookup_locked(to_email=customer_email, stripe_event_id=event_id) or elog

    provider_msg_id = ""
    try:
        if not license_key:
            raise ValueError("missing license_key")

        provider_msg_id = _send_license_key_email_best_effort(
            to_email=customer_email,
            customer_name=customer_name,
            license_key=license_key,
            tier=tier or plan_code,
            max_sites=max_sites_for_email,
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
        email_error = ""

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
        email_error = (str(e) or "")[:300]

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
                "email_error": email_error,
                "customer_db_id": customer_db_id,
                "plan_db_id": plan_db_id,
                "subscription_db_id": subscription_db_id,
                "entitlement_db_id": entitlement_db_id,
            },
        }
    )
