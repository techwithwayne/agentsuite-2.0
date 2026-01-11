# /home/techwithwayne/agentsuite/postpress_ai/views/stripe_webhook.py

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

2025-12-26.3
- ADD: Issue License on checkout.session.completed (idempotent).
- ADD: Email License key to purchaser.

2026-01-10.4
- FIX: Split fulfillment into two atomic blocks:
       (A) Order+License commit first (always persisted),
       (B) Command Center upserts + EmailLog+email (retryable on webhook retry).
- KEEP: Tier normalization to "Tyler" (locked intent).

2026-01-10.5
- FIX: Plan assignment defaulted to "solo" when Stripe metadata missing; now defaults to "tyler".
- FIX: Plan resolver only uses Plan fields that actually exist (your Plan has code+name).

2026-01-10.6  # CHANGED:
- FIX: Activation reads License fields; webhook now syncs License.plan_slug + limits/flags from Plan.  # CHANGED:
       (plan_slug/max_sites/unlimited_sites/byo_key_required/ai_included) when those fields exist.   # CHANGED:

2026-01-10.7  # CHANGED:
- ADD: Mode aliases + log-only visibility for which webhook secret env var is selected (no secret values).  # CHANGED:
- ADD: Keep Order.notes aligned with resolved tier+plan_code on webhook retries for auditing.             # CHANGED:
- TWEAK: Plan resolver accepts non-dict metadata safely + a couple extra key aliases.                    # CHANGED:

2026-01-11  # CHANGED:
- FIX: EmailLog idempotency lookup no longer assumes stripe_event_id column exists (pre-migration safe). # CHANGED:
- ADD: IntegrityError-safe EmailLog create: if unique constraint triggers, refetch + continue.          # CHANGED:
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import stripe
from django.db import IntegrityError, models, transaction  # CHANGED:
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from postpress_ai.license_keys import generate_unique_license_key
from postpress_ai.models.license import License
from postpress_ai.models.order import Order

# Command Center models
from postpress_ai.models.customer import Customer
from postpress_ai.models.plan import Plan
from postpress_ai.models.subscription import Subscription
from postpress_ai.models.entitlement import Entitlement
from postpress_ai.models.email_log import EmailLog

log = logging.getLogger("webdoctor")

WEBHOOK_VER = "stripe-webhook.v2026-01-11.1"  # CHANGED:
LICENSE_EMAIL_SUBJECT = "Welcome to PostPress AI — here’s your key"  # locked

DEFAULT_PLAN_CODE = "tyler"  # early-bird default plan code


# --------------------------------------------------------------------------------------
# Small utils (safe + schema tolerant)
# --------------------------------------------------------------------------------------

def _json_response(
    ok: bool,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
    status: int = 200,
) -> JsonResponse:
    return JsonResponse({"ok": bool(ok), "ver": WEBHOOK_VER, "data": data or {}, "error": error or {}}, status=status)


def _get_stripe_webhook_secret_info() -> tuple[str, str, str]:
    """
    Mode-aware webhook secret selection.

    Returns:
        (secret, source_env_var, mode)

    Priority:
    - If PPA_STRIPE_MODE is "live"/"prod"/"production" -> STRIPE_LIVE_WEBHOOK_SECRET
    - If PPA_STRIPE_MODE is "test"/"sandbox"          -> STRIPE_TEST_WEBHOOK_SECRET
    - Fallback                                        -> STRIPE_WEBHOOK_SECRET

    Notes:
    - We never log secret values, only which env var was used.
    """
    mode_raw = (os.environ.get("PPA_STRIPE_MODE") or "").strip().lower()

    # Normalize mode aliases (keeps ops human-friendly)
    if mode_raw in {"live", "prod", "production"}:
        mode = "live"
    elif mode_raw in {"test", "sandbox"}:
        mode = "test"
    elif mode_raw:
        # Unknown mode: keep fallback behavior but make it visible in logs.
        mode = mode_raw
    else:
        mode = ""

    if mode == "live":
        secret = (os.environ.get("STRIPE_LIVE_WEBHOOK_SECRET") or "").strip()
        if secret:
            return secret, "STRIPE_LIVE_WEBHOOK_SECRET", "live"

    if mode == "test":
        secret = (os.environ.get("STRIPE_TEST_WEBHOOK_SECRET") or "").strip()
        if secret:
            return secret, "STRIPE_TEST_WEBHOOK_SECRET", "test"

    secret = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("Missing Stripe webhook secret env var for current mode.")
    return secret, "STRIPE_WEBHOOK_SECRET", (mode or "fallback")


def _get_stripe_webhook_secret() -> str:
    # Backward-compat helper used by older code paths.
    secret, _src, _mode = _get_stripe_webhook_secret_info()
    return secret


def _safe_str(val: Any) -> str:
    try:
        return str(val)
    except Exception:
        return ""


def _to_plain_dict(obj: Any) -> Dict[str, Any]:
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


def _model_field_names(model_cls: type) -> set[str]:
    try:
        return {f.name for f in model_cls._meta.get_fields()}  # type: ignore[attr-defined]
    except Exception:
        return set()


def _has_field(model_cls: type, name: str) -> bool:
    return name in _model_field_names(model_cls)


def _set_if_field(obj: Any, field_name: str, value: Any) -> None:
    if value is None:
        return
    if _has_field(obj.__class__, field_name):
        setattr(obj, field_name, value)


def _get_const(cls: Any, const_name: str, default: str) -> str:
    return _safe_str(getattr(cls, const_name, default)) or default


def _pick_first_field(model_cls: type, candidates: list[str]) -> Optional[str]:
    names = _model_field_names(model_cls)
    for c in candidates:
        if c in names:
            return c
    return None


def _is_fk(model_cls: type, field_name: str) -> bool:
    try:
        f = model_cls._meta.get_field(field_name)  # type: ignore[attr-defined]
        return isinstance(f, models.ForeignKey)
    except Exception:
        return False


def _find_fk_to_order() -> Optional[str]:
    try:
        for f in License._meta.get_fields():  # type: ignore[attr-defined]
            if isinstance(f, models.ForeignKey) and getattr(f, "related_model", None) is Order:
                return f.name
    except Exception:
        return None
    return None


def _mask_key(k: str) -> str:
    k = (k or "").strip()
    if len(k) <= 8:
        return "***"
    return f"{k[:4]}…{k[-4:]}"


def _split_name(full_name: str) -> tuple[str, str]:
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""
    parts = full_name.split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last


# --------------------------------------------------------------------------------------
# Plan / Command Center mapping
# --------------------------------------------------------------------------------------

def _resolve_plan_code(metadata: Any) -> str:
    """
    Best-effort plan code resolver.

    Stripe Checkout sessions should include metadata.plan_code going forward,
    but we stay safe if it is missing (default plan code).

    Accepts:
      - dict-like metadata (preferred)
      - anything else (falls back safely)
    """
    md: dict[str, Any] = metadata if isinstance(metadata, dict) else {}

    for k in [
        "plan_code",
        "plan",
        "ppa_plan",
        "product_tier",
        "tier",
        "planCode",
        "ppaPlan",
    ]:
        v = (md.get(k) or "")
        if isinstance(v, str):
            v = v.strip().lower()
            if v:
                return v

    return DEFAULT_PLAN_CODE


def _resolve_or_create_plan(plan_code: str) -> Plan:
    """
    Resolve Plan using your actual Plan schema (code, name).
    """
    code = (plan_code or "").strip().lower() or DEFAULT_PLAN_CODE
    alias = {
        "unlimited": "agency_unlimited_byo",
        "agency_unlimited": "agency_unlimited_byo",
        "agency-byo": "agency_unlimited_byo",
        "byo": "agency_unlimited_byo",
    }.get(code)
    if alias:
        code = alias

    hit = Plan.objects.filter(code__iexact=code).first()
    if hit:
        return hit

    hit = Plan.objects.filter(name__iexact=code).first()
    if hit:
        return hit

    plan = Plan()
    if _has_field(Plan, "code"):
        plan.code = code
    if _has_field(Plan, "name") and not getattr(plan, "name", ""):
        plan.name = code.replace("_", " ").title()

    if _has_field(Plan, "is_active") and getattr(plan, "is_active", None) is None:
        plan.is_active = True
    if _has_field(Plan, "max_sites") and not getattr(plan, "max_sites", None):
        plan.max_sites = 1

    plan.save()
    return plan


def _sync_license_from_plan(*, lic: License, plan_code: str, plan: Plan, tier: str) -> None:
    dirty = False

    if _has_field(License, "plan_slug"):
        v = (getattr(lic, "plan_slug", "") or "").strip().lower()
        if v != (plan_code or "").strip().lower():
            setattr(lic, "plan_slug", (plan_code or "").strip().lower())
            dirty = True

    for f in ["plan_code", "plan"]:
        if _has_field(License, f) and not _is_fk(License, f):
            cur = (getattr(lic, f, "") or "").strip().lower()
            if cur != (plan_code or "").strip().lower():
                setattr(lic, f, (plan_code or "").strip().lower())
                dirty = True

    if _has_field(License, "max_sites") and _has_field(Plan, "max_sites"):
        try:
            pms = getattr(plan, "max_sites", None)
            if pms is not None and getattr(lic, "max_sites", None) != pms:
                setattr(lic, "max_sites", pms)
                dirty = True
        except Exception:
            pass

    if _has_field(License, "unlimited_sites") and _has_field(Plan, "max_sites"):
        try:
            pms = getattr(plan, "max_sites", None)
            unlimited = bool(pms == 0)
            if bool(getattr(lic, "unlimited_sites", False)) != unlimited:
                setattr(lic, "unlimited_sites", unlimited)
                dirty = True
        except Exception:
            pass

    if _has_field(Plan, "ai_mode"):
        try:
            ai_mode = (_safe_str(getattr(plan, "ai_mode", "")) or "").strip().lower()
            if _has_field(License, "byo_key_required"):
                byo = ("byo" in ai_mode)
                if bool(getattr(lic, "byo_key_required", False)) != byo:
                    setattr(lic, "byo_key_required", byo)
                    dirty = True
            if _has_field(License, "ai_included"):
                included = ("byo" not in ai_mode) and bool(ai_mode)
                if bool(getattr(lic, "ai_included", False)) != included:
                    setattr(lic, "ai_included", included)
                    dirty = True
        except Exception:
            pass

    if _has_field(License, "status"):
        try:
            if (getattr(lic, "status", "") or "").strip().lower() != "active":
                setattr(lic, "status", "active")
                dirty = True
        except Exception:
            pass

    if dirty:
        lic.save()


def _upsert_customer_from_order(order: Order) -> Customer:
    email = (order.purchaser_email or "").strip().lower()
    if not email:
        raise RuntimeError("Order missing purchaser_email; cannot upsert Customer.")

    if _has_field(Customer, "email"):
        customer = Customer.objects.filter(email=email).first()
        if not customer:
            customer = Customer()
            customer.email = email  # type: ignore[attr-defined]
    else:
        customer = Customer()

    full_name = (order.purchaser_name or "").strip()
    first, last = _split_name(full_name)

    _set_if_field(customer, "email", email)
    _set_if_field(customer, "name", full_name)
    _set_if_field(customer, "full_name", full_name)
    _set_if_field(customer, "first_name", first)
    _set_if_field(customer, "last_name", last)
    _set_if_field(customer, "source", "stripe_webhook")
    _set_if_field(customer, "last_seen_at", timezone.now())

    customer.save()
    return customer


def _upsert_subscription_for_session(*, customer: Customer, plan: Plan, session_obj: dict[str, Any]) -> Optional[Subscription]:
    session_id = _safe_str(session_obj.get("id"))
    stripe_customer_id = _safe_str(session_obj.get("customer"))
    stripe_subscription_id = _safe_str(session_obj.get("subscription"))
    stripe_payment_intent_id = _safe_str(session_obj.get("payment_intent"))

    session_field = _pick_first_field(Subscription, ["stripe_checkout_session_id", "stripe_session_id", "checkout_session_id", "session_id"])
    if not session_field:
        log.warning("PPA: Subscription model has no stripe session field; skipping Subscription upsert.")
        return None

    lookup = {session_field: session_id}
    sub = Subscription.objects.filter(**lookup).first()
    if not sub:
        sub = Subscription(**lookup)

    _set_if_field(sub, "customer", customer)
    _set_if_field(sub, "plan", plan)

    _set_if_field(sub, "stripe_customer_id", stripe_customer_id)
    _set_if_field(sub, "stripe_subscription_id", stripe_subscription_id)
    _set_if_field(sub, "stripe_payment_intent_id", stripe_payment_intent_id)

    status_active = _get_const(Subscription, "STATUS_ACTIVE", "active")
    _set_if_field(sub, "status", status_active)

    sub.save()
    return sub


def _upsert_entitlement(*, customer: Customer, plan: Plan, lic: License, sub: Optional[Subscription]) -> Entitlement:
    ent = None
    if _has_field(Entitlement, "license"):
        ent = Entitlement.objects.filter(license=lic).first()
    if not ent and _has_field(Entitlement, "customer") and _has_field(Entitlement, "plan"):
        ent = Entitlement.objects.filter(customer=customer, plan=plan).first()
    if not ent:
        ent = Entitlement()

    _set_if_field(ent, "customer", customer)
    _set_if_field(ent, "plan", plan)
    _set_if_field(ent, "license", lic)
    if sub is not None:
        _set_if_field(ent, "subscription", sub)

    status_active = _get_const(Entitlement, "STATUS_ACTIVE", "active")
    _set_if_field(ent, "status", status_active)
    _set_if_field(ent, "active", True)

    ent.save()
    return ent


def _elog_type_license_key() -> str:
    return _get_const(EmailLog, "TYPE_LICENSE_KEY", "license_key")


def _elog_status_sent() -> str:
    return _get_const(EmailLog, "STATUS_SENT", "sent")


def _elog_status_queued() -> str:
    return _get_const(EmailLog, "STATUS_QUEUED", "queued")


def _elog_status_failed() -> str:
    return _get_const(EmailLog, "STATUS_FAILED", _get_const(EmailLog, "STATUS_ERROR", "failed"))


def _email_log_lookup_locked(*, event_id: str, to_email: str) -> Optional[EmailLog]:
    event_id = (event_id or "").strip()
    to_email = (to_email or "").strip().lower()
    if not event_id or not to_email:
        return None

    # CHANGED: Do NOT assume stripe_event_id column exists.
    # We build the queryset safely, then add the right filter based on schema.
    qs = EmailLog.objects.select_for_update().filter(  # CHANGED:
        email_type=_elog_type_license_key(),
        to_email=to_email,
    )

    if _has_field(EmailLog, "stripe_event_id"):  # CHANGED:
        qs = qs.filter(stripe_event_id=event_id)  # CHANGED:
    elif _has_field(EmailLog, "meta"):
        qs = qs.filter(meta__stripe_event_id=event_id)  # CHANGED:

    return qs.order_by("-id").first()


def _email_is_inflight(elog: EmailLog) -> bool:
    try:
        if (getattr(elog, "status", "") or "").lower() != _elog_status_queued().lower():
            return False

        md = getattr(elog, "meta", {}) or {}
        queued_at = md.get("queued_at")
        if not queued_at:
            return True

        dt = timezone.datetime.fromisoformat(str(queued_at))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        age_seconds = (timezone.now() - dt).total_seconds()
        return age_seconds < 900
    except Exception:
        return True


def _send_license_email_with_log(*, event_id: str, order: Order, lic: License, license_key: str, product_tier: str, customer: Optional[Customer]) -> bool:
    to_email = (order.purchaser_email or "").strip().lower()
    if not to_email:
        return False

    with transaction.atomic():
        elog = _email_log_lookup_locked(event_id=event_id, to_email=to_email)

        if elog:
            if (getattr(elog, "status", "") or "").lower() == _elog_status_sent().lower():
                return True
            if _email_is_inflight(elog):
                return True
            _set_if_field(elog, "status", _elog_status_queued())
            _set_if_field(elog, "subject", LICENSE_EMAIL_SUBJECT)
            _set_if_field(elog, "customer", customer)
            if _has_field(EmailLog, "meta"):
                elog.meta = {**(elog.meta or {}), "queued_at": timezone.now().isoformat(), "retry": True}
            elog.save()
        else:
            elog = EmailLog()
            _set_if_field(elog, "customer", customer)
            _set_if_field(elog, "to_email", to_email)
            _set_if_field(elog, "subject", LICENSE_EMAIL_SUBJECT)
            _set_if_field(elog, "email_type", _elog_type_license_key())
            _set_if_field(elog, "provider", "sendgrid")
            _set_if_field(elog, "status", _elog_status_queued())
            if _has_field(EmailLog, "stripe_event_id"):
                elog.stripe_event_id = event_id  # type: ignore[attr-defined]
            if _has_field(EmailLog, "meta"):
                elog.meta = {
                    "stripe_event_id": event_id,
                    "queued_at": timezone.now().isoformat(),
                    "order_id": getattr(order, "id", None),
                    "license_id": getattr(lic, "id", None),
                    "license_last4": (license_key or "")[-4:],
                    "product_tier": product_tier,
                }

            # CHANGED: If you have a DB unique constraint on (stripe_event_id, to_email),
            # a concurrent webhook delivery might race here. If that happens, refetch the
            # locked row and proceed (no duplicate sends).
            try:  # CHANGED:
                elog.save()  # CHANGED:
            except IntegrityError:  # CHANGED:
                elog = _email_log_lookup_locked(event_id=event_id, to_email=to_email)  # CHANGED:
                if elog and (getattr(elog, "status", "") or "").lower() == _elog_status_sent().lower():  # CHANGED:
                    return True  # CHANGED:
                # If it's queued/failed, we fall through and send (idempotency is preserved).  # CHANGED:

    from postpress_ai.emailing import send_license_key_email  # lazy import

    message_id = f"<ppa-{(event_id or '').strip()}@postpressai.com>"
    kwargs = {
        "to_email": to_email,
        "license_key": license_key,
        "purchaser_name": order.purchaser_name or None,
        "product_tier": product_tier,
        "subject": LICENSE_EMAIL_SUBJECT,
        "headers": {"Message-ID": message_id},
    }

    try:
        send_license_key_email(**kwargs)

        with transaction.atomic():
            elog2 = _email_log_lookup_locked(event_id=event_id, to_email=to_email) or elog
            _set_if_field(elog2, "status", _elog_status_sent())
            _set_if_field(elog2, "sent_at", timezone.now())
            _set_if_field(elog2, "error", "")
            elog2.save()

        return True

    except Exception as e:
        with transaction.atomic():
            elog2 = _email_log_lookup_locked(event_id=event_id, to_email=to_email) or elog
            _set_if_field(elog2, "status", _elog_status_failed())
            _set_if_field(elog2, "error", _safe_str(e))
            elog2.save()
        raise


def _issue_or_get_license_for_order(
    *,
    order: Order,
    session_obj: Dict[str, Any],
    tier: str,
    plan_code: str,
) -> Tuple[License, bool, str]:
    key_field = _pick_first_field(License, ["license_key", "key", "code", "license", "license_code"])
    if not key_field:
        raise RuntimeError("License model has no recognizable key field (license_key/key/code/... ).")

    fk_order_field = _find_fk_to_order()
    session_id_field = _pick_first_field(License, ["stripe_session_id", "session_id", "stripe_checkout_session_id"])

    existing: Optional[License] = None
    if fk_order_field:
        existing = License.objects.filter(**{fk_order_field: order}).first()
    elif session_id_field:
        existing = License.objects.filter(**{session_id_field: order.stripe_session_id}).first()

    if existing:
        license_key_value = _safe_str(getattr(existing, key_field, ""))
        return existing, False, license_key_value

    def _exists(k: str) -> bool:
        return License.objects.filter(**{key_field: k}).exists()

    new_key = generate_unique_license_key(exists=_exists, prefix="PPA")

    kwargs: dict[str, Any] = {key_field: new_key}
    if fk_order_field:
        kwargs[fk_order_field] = order
    if session_id_field:
        kwargs[session_id_field] = order.stripe_session_id

    purchaser_email = order.purchaser_email or ""
    purchaser_name = order.purchaser_name or ""

    email_field = _pick_first_field(License, ["email", "customer_email", "purchaser_email"])
    name_field = _pick_first_field(License, ["name", "customer_name", "purchaser_name"])

    tier_field = _pick_first_field(License, ["tier", "product_tier", "edition"])
    plan_field = _pick_first_field(License, ["plan_code", "plan"])  # string field only

    status_field = _pick_first_field(License, ["status", "state"])
    raw_field = _pick_first_field(License, ["raw", "raw_payload", "raw_session", "metadata"])

    if email_field and purchaser_email:
        kwargs[email_field] = purchaser_email
    if name_field and purchaser_name:
        kwargs[name_field] = purchaser_name
    if tier_field and tier:
        kwargs[tier_field] = tier
    if plan_field and plan_code and not _is_fk(License, plan_field):
        kwargs[plan_field] = plan_code
    if status_field:
        kwargs[status_field] = "active"
    if raw_field:
        kwargs[raw_field] = _to_plain_dict(session_obj)

    lic = License.objects.create(**kwargs)
    return lic, True, new_key


def _handle_checkout_session_completed(event: Dict[str, Any]) -> Dict[str, Any]:
    obj = (event.get("data") or {}).get("object") or {}

    session_id = obj.get("id")
    if not session_id:
        raise RuntimeError("Missing checkout session id in event payload.")

    customer_details = obj.get("customer_details") or {}
    customer_email = customer_details.get("email") or obj.get("customer_email") or ""
    customer_name = customer_details.get("name") or ""

    payment_status = obj.get("payment_status")
    amount_total = obj.get("amount_total")
    currency = obj.get("currency")
    stripe_customer_id = obj.get("customer")
    stripe_payment_intent_id = obj.get("payment_intent")

    metadata = obj.get("metadata") or {}
    tier = "Tyler"  # LOCKED
    plan_code = _resolve_plan_code(metadata)

    event_id = _safe_str(event.get("id"))
    raw_event = _to_plain_dict(event)
    raw_session = _to_plain_dict(obj)

    normalized_status = "paid" if _safe_str(payment_status).lower() == "paid" else (_safe_str(payment_status) or "created")

    # (A) Persist Order+License first
    with transaction.atomic():
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
                "notes": (f"tier={tier} plan_code={plan_code}" if tier else None),
            },
        )

        if not created_order:
            dirty = False
            if event_id and not order.stripe_event_id:
                order.stripe_event_id = event_id
                dirty = True
            if customer_name and order.purchaser_name != _safe_str(customer_name):
                order.purchaser_name = _safe_str(customer_name)
                dirty = True
            if customer_email and order.purchaser_email != _safe_str(customer_email):
                order.purchaser_email = _safe_str(customer_email)
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

            try:
                new_notes = (f"tier={tier} plan_code={plan_code}" if tier else None)
                if new_notes is not None and (getattr(order, "notes", None) or "") != new_notes:
                    order.notes = new_notes  # type: ignore[attr-defined]
                    dirty = True
            except Exception:
                pass

            if dirty:
                order.save()

        lic, created_license, license_key = _issue_or_get_license_for_order(
            order=order,
            session_obj=obj,
            tier=tier,
            plan_code=plan_code,
        )

    # (B) Command Center + Email
    customer = None
    plan = None
    sub = None
    ent = None
    emailed = False

    if (order.purchaser_email or "").strip():
        with transaction.atomic():
            customer = _upsert_customer_from_order(order)
            plan = _resolve_or_create_plan(plan_code)
            sub = _upsert_subscription_for_session(customer=customer, plan=plan, session_obj=obj)
            ent = _upsert_entitlement(customer=customer, plan=plan, lic=lic, sub=sub)
            _sync_license_from_plan(lic=lic, plan_code=plan_code, plan=plan, tier=tier)

        emailed = _send_license_email_with_log(
            event_id=event_id,
            order=order,
            lic=lic,
            license_key=license_key,
            product_tier=tier,
            customer=customer,
        )

        with transaction.atomic():
            if emailed and order.status != "fulfilled":
                order.status = "fulfilled"
                order.save(update_fields=["status", "updated_at"])

    else:
        with transaction.atomic():
            if order.status != "paid_no_email":
                order.status = "paid_no_email"
                order.save(update_fields=["status", "updated_at"])

    log.info(
        "PPA Stripe webhook: session=%s order=%s license=%s created=%s emailed=%s key=%s plan_code=%s",
        _safe_str(session_id),
        getattr(order, "id", None),
        getattr(lic, "id", None),
        bool(created_license),
        bool(emailed),
        _mask_key(_safe_str(license_key)),
        plan_code,
    )

    return {
        "event": "checkout.session.completed",
        "session_id": session_id,
        "payment_status": payment_status,
        "email": customer_email,
        "tier": tier,
        "plan_code": plan_code,
        "order_db_id": getattr(order, "id", None),
        "order_created": bool(created_order),
        "order_status": order.status,
        "license_db_id": getattr(lic, "id", None),
        "license_created": bool(created_license),
        "license_emailed": bool(emailed),
        "license_key_masked": _mask_key(_safe_str(license_key)),
        "customer_db_id": getattr(customer, "id", None) if customer else None,
        "plan_db_id": getattr(plan, "id", None) if plan else None,
        "subscription_db_id": getattr(sub, "id", None) if sub else None,
        "entitlement_db_id": getattr(ent, "id", None) if ent else None,
    }


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _json_response(False, error={"code": "method_not_allowed", "message": "POST required."}, status=405)

    try:
        secret, secret_src, secret_mode = _get_stripe_webhook_secret_info()
        log.info("PPA Stripe webhook secret selected: mode=%s source=%s", secret_mode, secret_src)
    except Exception as e:
        log.error("PPA Stripe webhook misconfigured: %s", _safe_str(e))
        return _json_response(False, error={"code": "misconfigured", "message": "Webhook not configured."}, status=500)

    payload = request.body
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
            data = _handle_checkout_session_completed(_to_plain_dict(event))
            return _json_response(True, data=data, status=200)

        return _json_response(True, data={"event": event_type, "ignored": True}, status=200)

    except Exception as e:
        log.exception("PPA Stripe webhook: handler error type=%s", event_type)
        return _json_response(False, error={"code": "handler_error", "message": _safe_str(e), "event": event_type}, status=500)
