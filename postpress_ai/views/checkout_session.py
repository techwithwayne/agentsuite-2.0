# /home/techwithwayne/agentsuite/postpress_ai/views/checkout_session.py
"""postpress_ai.views.checkout_session

Create Stripe Checkout Sessions (Django authoritative).

Purpose
- Creates a Stripe Checkout Session for PostPress AI purchases.
- Returns { ok, data: { url, session_id }, error, ver } JSON.
- Keeps Stripe authority fully in Django (WordPress never talks to Stripe).

LOCKED RULES
- Stripe → Django is authoritative.
- WordPress never talks to Stripe.
- No browser secrets exposed.
- No CORS / ALLOWED_HOSTS widening here.

ENV
Required (recommended, mode-aware):
- PPA_STRIPE_MODE = "test" or "live" (defaults to "live")
- STRIPE_TEST_SECRET_KEY + PPA_STRIPE_TEST_PRICE_ID (when mode=test)
- STRIPE_LIVE_SECRET_KEY + PPA_STRIPE_LIVE_PRICE_ID (when mode=live)

Optional (subscription-only, Solo plan):
- PPA_STRIPE_TEST_PRICE_ID_SOLO (when mode=test)
- PPA_STRIPE_LIVE_PRICE_ID_SOLO (when mode=live)

Backward compatible (legacy):
- STRIPE_SECRET_KEY (required if mode-aware vars not set)
- PPA_STRIPE_PRICE_ID (required if mode-aware vars not set)  e.g. price_123...

Optional:
- PPA_STRIPE_SUCCESS_URL (defaults to https://postpressai.com/)
- PPA_STRIPE_CANCEL_URL  (defaults to https://postpressai.com/)
- PPA_CHECKOUT_RATE_LIMIT_PER_MIN (defaults to 20)

REQUEST
POST JSON body (common):
  {
    "email": "buyer@example.com",
    "name": "Buyer Name" (optional),
    "promo": "optional string",
    "success_url": "optional override",
    "cancel_url": "optional override",

    // Purchase kind (optional; inferred if omitted)
    "ppa_kind": "pack" | "subscription",

    // For packs (required for pack purchases)
    "license_key": "PPA-..." (or "ppa_license_key"),
    "pack_type": "small" (optional),

    // For subscriptions (optional)
    "plan_slug": "solo" (optional)
  }

NOTES
- For pack purchases: license_key is REQUIRED (so webhook can map pack → license).
- For subscription purchases: license_key is optional (webhook may create a new license).

========= CHANGE LOG =========
2025-12-27
- FIX: Idempotency key includes mode + success/cancel URLs to prevent Stripe idempotency_error 400s.
- ADD: Stripe test/live switching via PPA_STRIPE_MODE + mode-specific env vars.

2026-02-28
- ADD: ppa_kind support: pack (mode=payment) + subscription (mode=subscription).
- ADD: Solo plan price selection via PPA_STRIPE_*_PRICE_ID_SOLO.
- ADD: Pass-through metadata for license_key + pack/subscription details into Stripe objects.
- ADD: Guard: if ppa_kind=pack and missing license_key → 400 missing_license_key.

2026-02-28 (hotfix)
- FIX: Infer pack correctly even when pack_type is omitted (license_key is a pack signal).
- FIX: Append session_id param safely (handles existing query strings).
- SAFETY: subscription with no plan_slug defaults to solo (avoids accidental use of pack price id).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.utils.crypto import salted_hmac
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

VER = "checkout_session.v2.2026-02-28.2"

PPA_KIND_PACK = "pack"
PPA_KIND_SUBSCRIPTION = "subscription"


@dataclass(frozen=True)
class CheckoutConfig:
    secret_key: str
    default_price_id: str
    success_url: str
    cancel_url: str
    per_minute_limit: int
    mode: str


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _as_str(v: Any) -> str:
    """Best-effort stringify for Stripe metadata values."""
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _stripe_mode() -> str:
    """Returns normalized Stripe mode: "test" or "live"."""
    raw = (_env("PPA_STRIPE_MODE", "live") or "live").strip().lower()
    return "test" if raw == "test" else "live"


def _resolve_stripe_creds(mode: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve Stripe creds in the safest order:

    1) Mode-aware vars (recommended)
    2) Legacy vars (backward compatible)

    Returns (secret_key, default_price_id)
    """
    if mode == "test":
        secret_key = _env("STRIPE_TEST_SECRET_KEY")
        price_id = _env("PPA_STRIPE_TEST_PRICE_ID")
    else:  # live
        secret_key = _env("STRIPE_LIVE_SECRET_KEY")
        price_id = _env("PPA_STRIPE_LIVE_PRICE_ID")

    # Legacy fallback
    if not secret_key:
        secret_key = _env("STRIPE_SECRET_KEY")
    if not price_id:
        price_id = _env("PPA_STRIPE_PRICE_ID")

    return secret_key, price_id


def _get_checkout_config() -> CheckoutConfig:
    mode = _stripe_mode()
    secret_key, default_price_id = _resolve_stripe_creds(mode)

    success_url = _env("PPA_STRIPE_SUCCESS_URL", "https://postpressai.com/")
    cancel_url = _env("PPA_STRIPE_CANCEL_URL", "https://postpressai.com/")

    per_minute = int(_env("PPA_CHECKOUT_RATE_LIMIT_PER_MIN", "20"))

    missing = []
    if not secret_key:
        missing.append(
            ("STRIPE_TEST_SECRET_KEY" if mode == "test" else "STRIPE_LIVE_SECRET_KEY")
            + " (or STRIPE_SECRET_KEY legacy)"
        )
    if not default_price_id:
        missing.append(
            ("PPA_STRIPE_TEST_PRICE_ID" if mode == "test" else "PPA_STRIPE_LIVE_PRICE_ID")
            + " (or PPA_STRIPE_PRICE_ID legacy)"
        )

    if missing:
        raise RuntimeError(f"Missing required Stripe env vars for mode={mode}: {', '.join(missing)}")

    return CheckoutConfig(
        secret_key=secret_key,
        default_price_id=default_price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        per_minute_limit=per_minute,
        mode=mode,
    )


def _json_ok(data: Dict[str, Any]) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data, "error": None, "ver": VER}, status=200)


def _json_error(message: str, status: int, code: str = "error", detail: Optional[str] = None) -> JsonResponse:
    err: Dict[str, Any] = {"message": message, "code": code}
    if detail:
        err["detail"] = detail[:500]
    return JsonResponse({"ok": False, "data": None, "error": err, "ver": VER}, status=status)


def _get_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_key(ip: str) -> str:
    return f"ppa_checkout_rl:{ip}"


def _check_rate_limit(ip: str, limit_per_minute: int) -> Optional[JsonResponse]:
    key = _rate_limit_key(ip)
    count = cache.get(key, 0)
    try:
        count = int(count)
    except Exception:
        count = 0

    count += 1
    cache.set(key, count, timeout=60)

    if count > limit_per_minute:
        return _json_error(
            "Too many checkout attempts. Please try again in a minute.",
            429,
            code="rate_limited",
        )
    return None


def _parse_json_body(request: HttpRequest) -> Tuple[Optional[Dict[str, Any]], Optional[JsonResponse]]:
    try:
        raw = request.body.decode("utf-8") if request.body else ""
        if not raw.strip():
            return None, _json_error("Missing JSON body.", 400, code="missing_body")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None, _json_error("JSON body must be an object.", 400, code="invalid_json")
        return data, None
    except json.JSONDecodeError:
        return None, _json_error("Invalid JSON.", 400, code="invalid_json")
    except Exception:
        return None, _json_error("Unable to read request body.", 400, code="invalid_body")


def _safe_url(url: Optional[str], fallback: str) -> str:
    u = (url or "").strip()
    if not u:
        return fallback
    if not u.lower().startswith("https://"):
        return fallback
    return u


def _append_session_id_param(success_url: str) -> str:
    # Stripe replaces CHECKOUT_SESSION_ID; use & if query string already exists.
    joiner = "&" if "?" in success_url else "?"
    return f"{success_url}{joiner}session_id={{CHECKOUT_SESSION_ID}}"


def _infer_kind(data: Dict[str, Any]) -> str:
    raw = (data.get("ppa_kind") or data.get("kind") or data.get("purchase_kind") or "").strip().lower()
    if raw in (PPA_KIND_PACK, PPA_KIND_SUBSCRIPTION):
        return raw

    # Strong subscription signals
    plan_slug = (data.get("plan_slug") or data.get("ppa_plan_slug") or "").strip().lower()
    if plan_slug:
        return PPA_KIND_SUBSCRIPTION

    # Strong pack signal: license_key (pack requires it; subscription does not)
    license_key = (
        (data.get("license_key") or "").strip()
        or (data.get("ppa_license_key") or "").strip()
        or (data.get("key") or "").strip()
    )
    if license_key:
        return PPA_KIND_PACK

    # Other pack-ish signals
    pack_signals = [
        data.get("pack_type"),
        data.get("ppa_pack_type"),
        data.get("credits"),
        data.get("credits_granted"),
        data.get("pack"),
    ]
    if any(v not in (None, "", 0) for v in pack_signals):
        return PPA_KIND_PACK

    # Safer default: keep legacy behavior (endpoint historically used for packs)
    return PPA_KIND_PACK


def _resolve_price_id(cfg: CheckoutConfig, *, ppa_kind: str, plan_slug: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (price_id, missing_env_name_if_any)."""
    if ppa_kind != PPA_KIND_SUBSCRIPTION:
        return cfg.default_price_id, None

    slug = (plan_slug or "").strip().lower()
    if slug == "solo":
        if cfg.mode == "test":
            price_id = _env("PPA_STRIPE_TEST_PRICE_ID_SOLO")
            return (price_id, "PPA_STRIPE_TEST_PRICE_ID_SOLO") if not price_id else (price_id, None)
        price_id = _env("PPA_STRIPE_LIVE_PRICE_ID_SOLO")
        return (price_id, "PPA_STRIPE_LIVE_PRICE_ID_SOLO") if not price_id else (price_id, None)

    # If you add more plans later, handle them here.
    return None, "PPA_STRIPE_*_PRICE_ID_<PLAN>"


def _idempotency_key(
    *,
    email: str,
    price_id: str,
    ppa_kind: str,
    plan_slug: str,
    license_key: str,
    pack_type: str,
    stripe_mode: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Stripe idempotency keys MUST be reused only with identical parameters."""
    payload = "|".join(
        [
            stripe_mode,
            ppa_kind,
            (plan_slug or "").strip().lower(),
            (pack_type or "").strip().lower(),
            email.lower().strip(),
            (license_key or "").strip(),
            price_id,
            success_url,
            cancel_url,
        ]
    )
    digest = salted_hmac("ppa.checkout", payload, secret=None).hexdigest()
    return f"ppa_checkout_{digest[:40]}"


@csrf_exempt
@require_POST
def create_checkout_session(request: HttpRequest) -> JsonResponse:
    """Create a Stripe Checkout Session."""
    try:
        import stripe
    except Exception as e:
        logger.exception("Stripe import failed")
        return _json_error("Stripe library not installed on server.", 500, code="stripe_missing", detail=str(e))

    data, err = _parse_json_body(request)
    if err:
        return err
    assert data is not None

    email = (data.get("email") or "").strip()
    name = (data.get("name") or "").strip()
    promo = (data.get("promo") or "").strip()

    if not email or "@" not in email:
        return _json_error("Valid email is required.", 400, code="invalid_email")

    ppa_kind = _infer_kind(data)
    plan_slug = (data.get("plan_slug") or data.get("ppa_plan_slug") or "").strip().lower()

    license_key = (
        (data.get("license_key") or "").strip()
        or (data.get("ppa_license_key") or "").strip()
        or (data.get("key") or "").strip()
    )

    pack_type = (data.get("pack_type") or data.get("ppa_pack_type") or "").strip().lower()

    if ppa_kind == PPA_KIND_SUBSCRIPTION and not plan_slug:
        # Safety default: avoid accidentally trying to subscribe using a one-time pack price id.
        plan_slug = "solo"

    if ppa_kind == PPA_KIND_PACK and not license_key:
        return _json_error(
            "Missing license_key for token pack purchase.",
            400,
            code="missing_license_key",
        )

    try:
        cfg = _get_checkout_config()
    except RuntimeError as e:
        return _json_error(str(e), 500, code="misconfigured")

    price_id, missing_env = _resolve_price_id(cfg, ppa_kind=ppa_kind, plan_slug=plan_slug)
    if missing_env:
        return _json_error(
            f"Missing required Stripe env var for this purchase: {missing_env} (mode={cfg.mode}).",
            500,
            code="misconfigured",
        )
    if not price_id:
        return _json_error("Unable to resolve Stripe price id.", 500, code="misconfigured")

    ip = _get_ip(request)
    rl = _check_rate_limit(ip, cfg.per_minute_limit)
    if rl:
        return rl

    logger.info(
        "PPA checkout create: stripe_mode=%s kind=%s plan_slug=%s price_id=%s ip=%s",
        cfg.mode,
        ppa_kind,
        plan_slug,
        price_id,
        ip,
    )

    stripe.api_key = cfg.secret_key

    success_url = _safe_url(data.get("success_url"), cfg.success_url)
    cancel_url = _safe_url(data.get("cancel_url"), cfg.cancel_url)

    idem_key = _idempotency_key(
        email=email,
        price_id=price_id,
        ppa_kind=ppa_kind,
        plan_slug=plan_slug,
        license_key=license_key,
        pack_type=pack_type,
        stripe_mode=cfg.mode,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    session_md: Dict[str, str] = {
        "ppa_ver": VER,
        "ppa_kind": ppa_kind,
        "plan_slug": plan_slug,
        "pack_type": pack_type,
        "buyer_email": email,
        "buyer_name": name,
        "promo": promo,
        "ip": ip,
        "stripe_mode": cfg.mode,
    }
    if license_key:
        session_md["license_key"] = license_key

    obj_md: Dict[str, str] = {
        "ppa_ver": VER,
        "ppa_kind": ppa_kind,
        "plan_slug": plan_slug,
        "pack_type": pack_type,
        "buyer_email": email,
        "buyer_name": name,
        "stripe_mode": cfg.mode,
    }
    if license_key:
        obj_md["license_key"] = license_key

    session_md = {k: _as_str(v) for k, v in session_md.items() if _as_str(v) != ""}
    obj_md = {k: _as_str(v) for k, v in obj_md.items() if _as_str(v) != ""}

    try:
        common_kwargs: Dict[str, Any] = {
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": _append_session_id_param(success_url),
            "cancel_url": cancel_url,
            "customer_email": email,
            "allow_promotion_codes": True,
            "metadata": session_md,
            "client_reference_id": license_key or email,
            "idempotency_key": idem_key,
        }

        if ppa_kind == PPA_KIND_PACK:
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_intent_data={"metadata": obj_md},
                **common_kwargs,
            )
        else:
            session = stripe.checkout.Session.create(
                mode="subscription",
                subscription_data={"metadata": obj_md},
                **common_kwargs,
            )

        url = getattr(session, "url", None)
        sid = getattr(session, "id", None)
        if not url or not sid:
            return _json_error("Stripe did not return a session URL.", 502, code="stripe_no_url")

        return _json_ok({"url": url, "session_id": sid, "ppa_kind": ppa_kind, "plan_slug": plan_slug})

    except Exception as e:
        logger.exception("Stripe checkout session create failed")
        detail = str(e)
        try:
            if hasattr(e, "user_message") and getattr(e, "user_message"):
                detail = getattr(e, "user_message")
        except Exception:
            pass
        return _json_error("Unable to create checkout session.", 502, code="stripe_error", detail=detail)