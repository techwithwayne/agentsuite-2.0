# /home/techwithwayne/agentsuite/postpress_ai/views/checkout_session.py
"""
postpress_ai.views.checkout_session

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
- PPA_STRIPE_MODE = "test" or "live" (defaults to "live")                                        # CHANGED:
- STRIPE_TEST_SECRET_KEY + PPA_STRIPE_TEST_PRICE_ID (when mode=test)                             # CHANGED:
- STRIPE_LIVE_SECRET_KEY + PPA_STRIPE_LIVE_PRICE_ID (when mode=live)                             # CHANGED:

Backward compatible (legacy):
- STRIPE_SECRET_KEY (required if mode-aware vars not set)                                        # CHANGED:
- PPA_STRIPE_PRICE_ID (required if mode-aware vars not set)  e.g. price_123...                   # CHANGED:

Optional:
- PPA_STRIPE_SUCCESS_URL (defaults to https://postpressai.com/)
- PPA_STRIPE_CANCEL_URL  (defaults to https://postpressai.com/)
- PPA_CHECKOUT_RATE_LIMIT_PER_MIN (defaults to 20)

========= CHANGE LOG =========
2025-12-27
- FIX: Idempotency key now includes mode + success/cancel URLs to prevent Stripe idempotency_error 400s
       when parameters differ between attempts.                                                   # CHANGED:
- ADD: Stripe test/live mode switching via PPA_STRIPE_MODE + mode-specific env vars.              # CHANGED:
- KEEP: Backward compatibility with STRIPE_SECRET_KEY + PPA_STRIPE_PRICE_ID.                     # CHANGED:
- HARDEN: Return Stripe error detail + log exception safely (unblocks debugging 502s).           # CHANGED:
- KEEP: CSRF exempt checkout create endpoint (server-to-server + curl).                          # CHANGED:
- KEEP: cache-based rate limiting + idempotency key support.                                     # CHANGED:
- KEEP: safe response envelope {ok,data,error,ver}.                                              # CHANGED:
"""

from __future__ import annotations  # CHANGED:

import json  # CHANGED:
import logging  # CHANGED:
import os  # CHANGED:
from dataclasses import dataclass  # CHANGED:
from typing import Any, Dict, Optional, Tuple  # CHANGED:

from django.core.cache import cache  # CHANGED:
from django.http import HttpRequest, JsonResponse  # CHANGED:
from django.utils.crypto import salted_hmac  # CHANGED:
from django.views.decorators.http import require_POST  # CHANGED:
from django.views.decorators.csrf import csrf_exempt  # CHANGED:

logger = logging.getLogger(__name__)  # CHANGED:

VER = "checkout_session.v1.2025-12-27.3"  # CHANGED: bump for visibility


@dataclass(frozen=True)  # CHANGED:
class CheckoutConfig:  # CHANGED:
    secret_key: str  # CHANGED:
    price_id: str  # CHANGED:
    success_url: str  # CHANGED:
    cancel_url: str  # CHANGED:
    per_minute_limit: int  # CHANGED:
    mode: str  # CHANGED:


def _env(name: str, default: Optional[str] = None) -> Optional[str]:  # CHANGED:
    val = os.environ.get(name)  # CHANGED:
    return val if val not in (None, "") else default  # CHANGED:


def _stripe_mode() -> str:  # CHANGED:
    """
    Returns normalized Stripe mode: "test" or "live".
    Defaults to "live" if unset/invalid (production-safe default).
    """  # CHANGED:
    raw = (_env("PPA_STRIPE_MODE", "live") or "live").strip().lower()  # CHANGED:
    return "test" if raw == "test" else "live"  # CHANGED:


def _resolve_stripe_creds(mode: str) -> Tuple[Optional[str], Optional[str]]:  # CHANGED:
    """
    Resolve Stripe creds in the safest order:
    1) Mode-aware vars (recommended)
    2) Legacy vars (backward compatible)

    Returns (secret_key, price_id)
    """  # CHANGED:
    if mode == "test":  # CHANGED:
        secret_key = _env("STRIPE_TEST_SECRET_KEY")  # CHANGED:
        price_id = _env("PPA_STRIPE_TEST_PRICE_ID")  # CHANGED:
    else:  # live  # CHANGED:
        secret_key = _env("STRIPE_LIVE_SECRET_KEY")  # CHANGED:
        price_id = _env("PPA_STRIPE_LIVE_PRICE_ID")  # CHANGED:

    # Backward compatible fallback (keeps legacy setups intact).  # CHANGED:
    if not secret_key:  # CHANGED:
        secret_key = _env("STRIPE_SECRET_KEY")  # CHANGED:
    if not price_id:  # CHANGED:
        price_id = _env("PPA_STRIPE_PRICE_ID")  # CHANGED:

    return secret_key, price_id  # CHANGED:


def _get_checkout_config() -> CheckoutConfig:  # CHANGED:
    mode = _stripe_mode()  # CHANGED:
    secret_key, price_id = _resolve_stripe_creds(mode)  # CHANGED:

    success_url = _env("PPA_STRIPE_SUCCESS_URL", "https://postpressai.com/")  # CHANGED:
    cancel_url = _env("PPA_STRIPE_CANCEL_URL", "https://postpressai.com/")  # CHANGED:

    per_minute = int(_env("PPA_CHECKOUT_RATE_LIMIT_PER_MIN", "20"))  # CHANGED:

    missing = []  # CHANGED:
    if not secret_key:  # CHANGED:
        if mode == "test":  # CHANGED:
            missing.append("STRIPE_TEST_SECRET_KEY (or STRIPE_SECRET_KEY legacy)")  # CHANGED:
        else:  # CHANGED:
            missing.append("STRIPE_LIVE_SECRET_KEY (or STRIPE_SECRET_KEY legacy)")  # CHANGED:
    if not price_id:  # CHANGED:
        if mode == "test":  # CHANGED:
            missing.append("PPA_STRIPE_TEST_PRICE_ID (or PPA_STRIPE_PRICE_ID legacy)")  # CHANGED:
        else:  # CHANGED:
            missing.append("PPA_STRIPE_LIVE_PRICE_ID (or PPA_STRIPE_PRICE_ID legacy)")  # CHANGED:

    if missing:  # CHANGED:
        raise RuntimeError(f"Missing required Stripe env vars for mode={mode}: {', '.join(missing)}")  # CHANGED:

    return CheckoutConfig(  # CHANGED:
        secret_key=secret_key,  # CHANGED:
        price_id=price_id,  # CHANGED:
        success_url=success_url,  # CHANGED:
        cancel_url=cancel_url,  # CHANGED:
        per_minute_limit=per_minute,  # CHANGED:
        mode=mode,  # CHANGED:
    )  # CHANGED:


def _json_ok(data: Dict[str, Any]) -> JsonResponse:  # CHANGED:
    return JsonResponse({"ok": True, "data": data, "error": None, "ver": VER}, status=200)  # CHANGED:


def _json_error(message: str, status: int, code: str = "error", detail: Optional[str] = None) -> JsonResponse:  # CHANGED:
    err: Dict[str, Any] = {"message": message, "code": code}  # CHANGED:
    if detail:  # CHANGED:
        err["detail"] = detail[:500]  # CHANGED:
    return JsonResponse({"ok": False, "data": None, "error": err, "ver": VER}, status=status)  # CHANGED:


def _get_ip(request: HttpRequest) -> str:  # CHANGED:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")  # CHANGED:
    if xff:  # CHANGED:
        return xff.split(",")[0].strip()  # CHANGED:
    return request.META.get("REMOTE_ADDR", "unknown")  # CHANGED:


def _rate_limit_key(ip: str) -> str:  # CHANGED:
    return f"ppa_checkout_rl:{ip}"  # CHANGED:


def _check_rate_limit(ip: str, limit_per_minute: int) -> Optional[JsonResponse]:  # CHANGED:
    key = _rate_limit_key(ip)  # CHANGED:
    count = cache.get(key, 0)  # CHANGED:
    try:  # CHANGED:
        count = int(count)  # CHANGED:
    except Exception:  # CHANGED:
        count = 0  # CHANGED:

    count += 1  # CHANGED:
    cache.set(key, count, timeout=60)  # CHANGED:

    if count > limit_per_minute:  # CHANGED:
        return _json_error(
            "Too many checkout attempts. Please try again in a minute.",
            429,
            code="rate_limited",
        )  # CHANGED:
    return None  # CHANGED:


def _parse_json_body(request: HttpRequest) -> Tuple[Optional[Dict[str, Any]], Optional[JsonResponse]]:  # CHANGED:
    try:  # CHANGED:
        raw = request.body.decode("utf-8") if request.body else ""  # CHANGED:
        if not raw.strip():  # CHANGED:
            return None, _json_error("Missing JSON body.", 400, code="missing_body")  # CHANGED:
        data = json.loads(raw)  # CHANGED:
        if not isinstance(data, dict):  # CHANGED:
            return None, _json_error("JSON body must be an object.", 400, code="invalid_json")  # CHANGED:
        return data, None  # CHANGED:
    except json.JSONDecodeError:  # CHANGED:
        return None, _json_error("Invalid JSON.", 400, code="invalid_json")  # CHANGED:
    except Exception:  # CHANGED:
        return None, _json_error("Unable to read request body.", 400, code="invalid_body")  # CHANGED:


def _safe_url(url: Optional[str], fallback: str) -> str:  # CHANGED:
    u = (url or "").strip()  # CHANGED:
    if not u:  # CHANGED:
        return fallback  # CHANGED:
    if not u.lower().startswith("https://"):  # CHANGED:
        return fallback  # CHANGED:
    return u  # CHANGED:


def _idempotency_key(email: str, price_id: str, mode: str, success_url: str, cancel_url: str) -> str:  # CHANGED:
    """
    Stripe idempotency keys MUST be reused only with identical parameters.
    We therefore hash the fields most likely to vary between attempts (mode + URLs).             # CHANGED:
    """  # CHANGED:
    payload = f"{mode}|{email.lower().strip()}|{price_id}|{success_url}|{cancel_url}"  # CHANGED:
    digest = salted_hmac("ppa.checkout", payload, secret=None).hexdigest()  # CHANGED:
    return f"ppa_checkout_{digest[:40]}"  # CHANGED:


@csrf_exempt  # CHANGED:
@require_POST  # CHANGED:
def create_checkout_session(request: HttpRequest) -> JsonResponse:  # CHANGED:
    """
    POST JSON body:
      {
        "email": "buyer@example.com",
        "name": "Buyer Name" (optional),
        "promo": "optional string",
        "success_url": "optional override",
        "cancel_url": "optional override"
      }
    """
    try:  # CHANGED:
        import stripe  # CHANGED:
    except Exception as e:  # CHANGED:
        logger.exception("Stripe import failed")  # CHANGED:
        return _json_error("Stripe library not installed on server.", 500, code="stripe_missing", detail=str(e))  # CHANGED:

    data, err = _parse_json_body(request)  # CHANGED:
    if err:  # CHANGED:
        return err  # CHANGED:
    assert data is not None  # CHANGED:

    email = (data.get("email") or "").strip()  # CHANGED:
    name = (data.get("name") or "").strip()  # CHANGED:
    promo = (data.get("promo") or "").strip()  # CHANGED:

    if not email or "@" not in email:  # CHANGED:
        return _json_error("Valid email is required.", 400, code="invalid_email")  # CHANGED:

    try:  # CHANGED:
        cfg = _get_checkout_config()  # CHANGED:
    except RuntimeError as e:  # CHANGED:
        return _json_error(str(e), 500, code="misconfigured")  # CHANGED:

    ip = _get_ip(request)  # CHANGED:
    rl = _check_rate_limit(ip, cfg.per_minute_limit)  # CHANGED:
    if rl:  # CHANGED:
        return rl  # CHANGED:

    logger.info("PPA checkout create: mode=%s price_id=%s ip=%s", cfg.mode, cfg.price_id, ip)  # CHANGED:

    stripe.api_key = cfg.secret_key  # CHANGED:

    success_url = _safe_url(data.get("success_url"), cfg.success_url)  # CHANGED:
    cancel_url = _safe_url(data.get("cancel_url"), cfg.cancel_url)  # CHANGED:

    idem_key = _idempotency_key(email, cfg.price_id, cfg.mode, success_url, cancel_url)  # CHANGED:

    try:  # CHANGED:
        session = stripe.checkout.Session.create(  # CHANGED:
            mode="payment",  # CHANGED:
            line_items=[{"price": cfg.price_id, "quantity": 1}],  # CHANGED:
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",  # CHANGED:
            cancel_url=cancel_url,  # CHANGED:
            customer_email=email,  # CHANGED:
            allow_promotion_codes=True,  # CHANGED:
            metadata={  # CHANGED:
                "ppa_ver": VER,  # CHANGED:
                "buyer_email": email,  # CHANGED:
                "buyer_name": name,  # CHANGED:
                "promo": promo,  # CHANGED:
                "ip": ip,  # CHANGED:
                "stripe_mode": cfg.mode,  # CHANGED:
            },  # CHANGED:
            client_reference_id=email,  # CHANGED:
            payment_intent_data={  # CHANGED:
                "metadata": {  # CHANGED:
                    "ppa_ver": VER,  # CHANGED:
                    "buyer_email": email,  # CHANGED:
                    "buyer_name": name,  # CHANGED:
                    "stripe_mode": cfg.mode,  # CHANGED:
                }  # CHANGED:
            },  # CHANGED:
            idempotency_key=idem_key,  # CHANGED:
        )

        url = getattr(session, "url", None)  # CHANGED:
        sid = getattr(session, "id", None)  # CHANGED:
        if not url or not sid:  # CHANGED:
            return _json_error("Stripe did not return a session URL.", 502, code="stripe_no_url")  # CHANGED:

        return _json_ok({"url": url, "session_id": sid})  # CHANGED:

    except Exception as e:  # CHANGED:
        logger.exception("Stripe checkout session create failed")  # CHANGED:
        detail = str(e)  # CHANGED:
        try:  # CHANGED:
            if hasattr(e, "user_message") and getattr(e, "user_message"):  # CHANGED:
                detail = getattr(e, "user_message")  # CHANGED:
        except Exception:  # CHANGED:
            pass  # CHANGED:
        return _json_error("Unable to create checkout session.", 502, code="stripe_error", detail=detail)  # CHANGED:
