# /home/techwithwayne/agentsuite/postpress_ai/views/checkout_session.py
"""postpress_ai.views.checkout_session

Create Stripe Checkout Sessions (Django authoritative).

Purpose
- Creates a Stripe Checkout Session for PostPress AI purchases.
- Returns { ok, data: { url, session_id }, error, ver } JSON.
- Keeps Stripe authority fully in Django (WordPress never talks to Stripe).

ENV (CRUNCH-SAFE)
Required:
- PPA_STRIPE_MODE = "test" or "live" (defaults to "live")
- Stripe secret key for current mode:
  - STRIPE_TEST_SECRET_KEY (test)
  - STRIPE_LIVE_SECRET_KEY (live)
  - (legacy fallback) STRIPE_SECRET_KEY

Prices (ONE env var, all plans + all packs):
- PPA_STRIPE_PRICE_MAP  (JSON)

Recommended structure:
{
  "test": {
    "pack_default": "price_...",
    "pack_small":   "price_...",
    "pack_large":   "price_...",

    "sub_default":  "price_...",
    "solo_monthly": "price_...",
    "tyler_monthly":"price_...",
    "agency_monthly":"price_...",
    "byo_monthly":  "price_..."
  },
  "live": {
    "pack_default": "price_...",
    "pack_small":   "price_...",
    "pack_large":   "price_...",

    "sub_default":  "price_...",
    "solo_monthly": "price_...",
    "tyler_monthly":"price_...",
    "agency_monthly":"price_...",
    "byo_monthly":  "price_..."
  }
}

Key resolution rules:
- pack uses: pack_<pack_type> then pack_default (or pack/default/default_price)
- subscription uses:
  <plan_slug>_<billing_period> (billing_period default "monthly")
  then <plan_slug>
  then sub_default

Legacy (kept for backward compatibility during launch):
- Pack default: PPA_STRIPE_TEST_PRICE_ID / PPA_STRIPE_LIVE_PRICE_ID / PPA_STRIPE_PRICE_ID
- Solo only:    PPA_STRIPE_TEST_PRICE_ID_SOLO / PPA_STRIPE_LIVE_PRICE_ID_SOLO

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

    // For subscriptions
    "plan_slug": "solo" | "tyler" | "agency" | "byo" | ...,
    "billing_period": "monthly" (optional; default monthly)
  }

NOTES
- For pack purchases: license_key is REQUIRED (so webhook can map pack → license).
- For subscription purchases: license_key is optional (webhook may create a new license).
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

VER = "checkout_session.v2.2026-02-28.4"

PPA_KIND_PACK = "pack"
PPA_KIND_SUBSCRIPTION = "subscription"


@dataclass(frozen=True)
class CheckoutConfig:
    secret_key: str
    default_pack_price_id: str
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


def _load_price_map() -> Dict[str, Any]:
    """Loads PPA_STRIPE_PRICE_MAP JSON, returns {} on missing/invalid."""
    raw = _env("PPA_STRIPE_PRICE_MAP")
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        logger.warning("PPA_STRIPE_PRICE_MAP is not a JSON object")
        return {}
    except Exception as e:
        logger.warning("Invalid PPA_STRIPE_PRICE_MAP JSON: %s", str(e))
        return {}


def _price_bucket_for_mode(mode: str) -> Dict[str, str]:
    """Returns the dict of prices for the given mode."""
    pm = _load_price_map()
    if not pm:
        return {}

    # Preferred: {"test": {...}, "live": {...}}
    if mode in pm and isinstance(pm.get(mode), dict):
        bucket = pm.get(mode) or {}
        return {k: _as_str(v).strip() for k, v in bucket.items() if _as_str(v).strip()}

    # Fallback: allow a flat mapping for single-mode deployments
    if all(isinstance(v, (str, int, float)) for v in pm.values()):
        return {k: _as_str(v).strip() for k, v in pm.items() if _as_str(v).strip()}

    return {}


def _price_from_bucket(bucket: Dict[str, str], keys: Tuple[str, ...]) -> Optional[str]:
    for k in keys:
        v = (bucket.get(k) or "").strip()
        if v:
            return v
    return None


def _resolve_stripe_creds(mode: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve Stripe creds in the safest order:

    Secret:
    1) Mode-aware vars (recommended)
    2) Legacy STRIPE_SECRET_KEY

    Default pack price:
    1) PPA_STRIPE_PRICE_MAP for current mode (pack_default / pack / default / default_price)
    2) Legacy mode-aware price vars
    3) Legacy PPA_STRIPE_PRICE_ID
    """
    # Secret key
    if mode == "test":
        secret_key = _env("STRIPE_TEST_SECRET_KEY")
    else:
        secret_key = _env("STRIPE_LIVE_SECRET_KEY")
    if not secret_key:
        secret_key = _env("STRIPE_SECRET_KEY")

    # Default pack price id
    bucket = _price_bucket_for_mode(mode)
    price_id = _price_from_bucket(bucket, ("pack_default", "pack", "default", "default_price"))

    # Legacy fallback
    if not price_id:
        if mode == "test":
            price_id = _env("PPA_STRIPE_TEST_PRICE_ID")
        else:
            price_id = _env("PPA_STRIPE_LIVE_PRICE_ID")
    if not price_id:
        price_id = _env("PPA_STRIPE_PRICE_ID")

    return secret_key, price_id


def _get_checkout_config() -> CheckoutConfig:
    mode = _stripe_mode()
    secret_key, default_pack_price_id = _resolve_stripe_creds(mode)

    success_url = _env("PPA_STRIPE_SUCCESS_URL", "https://postpressai.com/")
    cancel_url = _env("PPA_STRIPE_CANCEL_URL", "https://postpressai.com/")

    per_minute = int(_env("PPA_CHECKOUT_RATE_LIMIT_PER_MIN", "20"))

    missing = []
    if not secret_key:
        missing.append(
            ("STRIPE_TEST_SECRET_KEY" if mode == "test" else "STRIPE_LIVE_SECRET_KEY")
            + " (or STRIPE_SECRET_KEY legacy)"
        )
    if not default_pack_price_id:
        missing.append("PPA_STRIPE_PRICE_MAP[mode].pack_default (or legacy PPA_STRIPE_*_PRICE_ID)")

    if missing:
        raise RuntimeError(f"Missing required Stripe env vars for mode={mode}: {', '.join(missing)}")

    return CheckoutConfig(
        secret_key=secret_key,
        default_pack_price_id=default_pack_price_id,
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
        err["detail"] = detail[:900]
    return JsonResponse({"ok": False, "data": None, "error": err, "ver": VER}, status=status)


def _get_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _check_rate_limit(ip: str, limit_per_minute: int) -> Optional[JsonResponse]:
    key = f"ppa_checkout_rl:{ip}"
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
    # If caller already provided the placeholder, leave it alone.
    if "{CHECKOUT_SESSION_ID}" in success_url:
        return success_url
    joiner = "&" if "?" in success_url else "?"
    return f"{success_url}{joiner}session_id={{CHECKOUT_SESSION_ID}}"


def _infer_kind(data: Dict[str, Any]) -> str:
    raw = (data.get("ppa_kind") or data.get("kind") or data.get("purchase_kind") or "").strip().lower()
    if raw in (PPA_KIND_PACK, PPA_KIND_SUBSCRIPTION):
        return raw

    # Strong subscription signal
    plan_slug = (data.get("plan_slug") or data.get("ppa_plan_slug") or "").strip()
    if plan_slug:
        return PPA_KIND_SUBSCRIPTION

    # Strong pack signal (packs require license_key)
    license_key = (
        (data.get("license_key") or "").strip()
        or (data.get("ppa_license_key") or "").strip()
        or (data.get("key") or "").strip()
    )
    if license_key:
        return PPA_KIND_PACK

    # Otherwise: pack (endpoint historically used for packs; safer default)
    return PPA_KIND_PACK


def _resolve_price_id(
    cfg: CheckoutConfig,
    *,
    ppa_kind: str,
    plan_slug: str,
    billing_period: str,
    pack_type: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Returns (price_id, missing_hint)."""
    bucket = _price_bucket_for_mode(cfg.mode)

    if ppa_kind == PPA_KIND_PACK:
        # Prefer explicit pack mapping: pack_small, pack_large, etc.
        pt = (pack_type or "").strip().lower()
        if pt:
            price_id = _price_from_bucket(bucket, (f"pack_{pt}",))
            if price_id:
                return price_id, None

        # Fallbacks
        price_id = _price_from_bucket(bucket, ("pack_default", "pack", "default", "default_price"))
        if price_id:
            return price_id, None

        # Final fallback: legacy default pack price
        return cfg.default_pack_price_id, None

    # Subscription
    slug = (plan_slug or "").strip().lower()
    if not slug:
        return None, "Missing plan_slug for subscription"

    period = (billing_period or "monthly").strip().lower()
    key1 = f"{slug}_{period}"
    key2 = slug
    price_id = _price_from_bucket(bucket, (key1, key2, "sub_default"))
    if price_id:
        return price_id, None

    # Legacy solo fallback (kept during launch)
    if slug == "solo":
        legacy = _env("PPA_STRIPE_TEST_PRICE_ID_SOLO") if cfg.mode == "test" else _env("PPA_STRIPE_LIVE_PRICE_ID_SOLO")
        if legacy:
            return legacy, None
        return None, f"PPA_STRIPE_PRICE_MAP[{cfg.mode}].solo_monthly missing (or legacy SOLO price env missing)"

    return None, f"PPA_STRIPE_PRICE_MAP[{cfg.mode}].{key1} missing (or .{key2} / sub_default missing)"


def _idempotency_key(
    *,
    email: str,
    price_id: str,
    ppa_kind: str,
    plan_slug: str,
    billing_period: str,
    license_key: str,
    pack_type: str,
    stripe_mode: str,
    success_url: str,
    cancel_url: str,
) -> str:
    payload = "|".join(
        [
            stripe_mode,
            ppa_kind,
            (plan_slug or "").strip().lower(),
            (billing_period or "").strip().lower(),
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
    billing_period = (data.get("billing_period") or data.get("ppa_billing_period") or "monthly").strip().lower()

    license_key = (
        (data.get("license_key") or "").strip()
        or (data.get("ppa_license_key") or "").strip()
        or (data.get("key") or "").strip()
    )

    pack_type = (data.get("pack_type") or data.get("ppa_pack_type") or "").strip().lower()

    if ppa_kind == PPA_KIND_PACK and not license_key:
        return _json_error("Missing license_key for token pack purchase.", 400, code="missing_license_key")

    try:
        cfg = _get_checkout_config()
    except RuntimeError as e:
        return _json_error(str(e), 500, code="misconfigured")

    price_id, missing_hint = _resolve_price_id(
        cfg,
        ppa_kind=ppa_kind,
        plan_slug=plan_slug,
        billing_period=billing_period,
        pack_type=pack_type,
    )
    if missing_hint and not price_id:
        return _json_error("Missing required Stripe price config.", 500, code="misconfigured", detail=missing_hint)
    if not price_id:
        return _json_error("Unable to resolve Stripe price id.", 500, code="misconfigured")

    ip = _get_ip(request)
    rl = _check_rate_limit(ip, cfg.per_minute_limit)
    if rl:
        return rl

    stripe.api_key = cfg.secret_key

    success_url = _safe_url(data.get("success_url"), cfg.success_url)
    cancel_url = _safe_url(data.get("cancel_url"), cfg.cancel_url)

    idem_key = _idempotency_key(
        email=email,
        price_id=price_id,
        ppa_kind=ppa_kind,
        plan_slug=plan_slug,
        billing_period=billing_period,
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
        "billing_period": billing_period,
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
        "billing_period": billing_period,
        "pack_type": pack_type,
        "buyer_email": email,
        "buyer_name": name,
        "stripe_mode": cfg.mode,
    }
    if license_key:
        obj_md["license_key"] = license_key

    session_md = {k: _as_str(v) for k, v in session_md.items() if _as_str(v)}
    obj_md = {k: _as_str(v) for k, v in obj_md.items() if _as_str(v)}

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