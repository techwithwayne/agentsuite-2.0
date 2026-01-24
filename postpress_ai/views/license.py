"""
postpress_ai.views.license

Licensing endpoints (Django is authoritative):
- /license/activate/
- /license/verify/
- /license/deactivate/

LOCKED RULES
- WordPress never decides license validity.
- WP → admin-ajax → PHP controller → Django only.
- No CORS / ALLOWED_HOSTS widening.
- Strict server-side (no grace period by default).

OPTION A (Customer-friendly auth)
- Customers SHOULD NOT need a shared key on every WordPress site.
- These license endpoints accept license_key + site_url WITHOUT requiring X-PPA-Key (shared key).
- Shared key auth remains supported as an OPTIONAL internal/proxy path.

Response envelope (consistent):
  { "ok": true|false, "data": {...}, "error": {...}, "ver": "license.v1" }
"""

from __future__ import annotations

# ========= CHANGE LOG =========
# 2025-12-24: Initial implementation of licensing endpoints with strict validation, shared-key auth,
#            URL normalization, activation limits, and cache-based rate limiting.
# 2025-12-24: Auth source corrected: shared key is read from os.environ["PPA_SHARED_KEY"] only.
#            (Matches hardened proxy behavior: tests must patch os.environ, not settings.)
# 2025-12-24: Deactivate is allowed even if license is inactive/expired (cleanup-safe + idempotent).
# 2025-12-24: Harden auth compare: normalize header/env values + constant-time compare (prevents false 401s).
# 2025-12-24: FIX: Enforce LOCKED env auth semantic: read via os.environ["PPA_SHARED_KEY"] (not .get()).
# 2026-01-04: OPTION A: Allow license endpoints to authenticate via license_key + site_url (no shared key).
#            Shared key remains an optional/internal path. No response shape changes.
# 2026-01-11: FIX: Repair broken license_deactivate docstring (stray triple-quote + auth block).
# 2026-01-24: HARDEN: /license/verify/ now returns deterministic, cache-friendly license status
#            including sites snapshot + token snapshot + cache TTL + server_time.             # CHANGED:
# 2026-01-24: HARDEN: Throttle last_verified_at writes on verify to improve cacheability and reduce DB churn. # CHANGED:
# 2026-01-24: FIX: AI-included plans must not return monthly_limit=0 (treat 0 as "unset" and fall back).    # CHANGED:
# 2026-01-24: FIX: Add 'tyler' to PLAN_DEFAULTS so early bird licenses get sane defaults.                    # CHANGED:

import hmac
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from django.core.cache import cache
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from postpress_ai.models.activation import Activation
from postpress_ai.models.license import License

API_VER = "license.v1"

# ------------------------------
# Rate limit (cache-based)
# ------------------------------
RL_WINDOW_SECONDS = 60
RL_IP_LIMIT_PER_WINDOW = 30  # per endpoint per IP per minute
RL_KEY_LIMIT_PER_WINDOW = 12  # per endpoint per license key per minute

# ------------------------------
# Verify caching / determinism
# ------------------------------
VERIFY_CACHE_TTL_SECONDS = 300  # 5 minutes  # CHANGED:
VERIFY_TOUCH_MIN_SECONDS = 600  # 10 minutes (throttle DB writes from verify)  # CHANGED:

# ------------------------------
# Plan defaults (fallback only)
# Django remains authoritative; if License has explicit fields set, those win.
# ------------------------------
PLAN_DEFAULTS = {  # CHANGED:
    # slug: (max_sites, unlimited, monthly_tokens, ai_included, byo_required)
    "tyler": (3, False, 500_000, True, False),  # CHANGED: early bird aligned to "creator" class tokens
    "solo": (1, False, 200_000, True, False),
    "creator": (3, False, 500_000, True, False),
    "studio": (10, False, 1_500_000, True, False),
    "agency": (25, False, 4_000_000, True, False),
    "agency_byo": (0, True, 0, False, True),  # Unlimited sites, BYO key, no included tokens
}


@dataclass(frozen=True)
class APIError(Exception):
    """Internal exception for consistent JSON error responses."""

    code: str
    message: str
    http_status: int = 400
    err_type: str = "validation_error"


# ------------------------------
# Helpers
# ------------------------------
def _json_ok(data: Dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True, "data": data, "ver": API_VER}, status=status)


def _json_err(e: APIError) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": {
                "type": e.err_type,
                "code": e.code,
                "message": e.message,
            },
            "ver": API_VER,
        },
        status=e.http_status,
    )


def _get_client_ip(request: HttpRequest) -> str:
    """
    Conservative IP extraction.
    We DO NOT trust X-Forwarded-For here unless you explicitly want to later, behind a known proxy.
    """
    ip = request.META.get("REMOTE_ADDR") or ""
    return ip.strip()[:64] if ip else "unknown"


def _norm(value: Any) -> str:
    """
    Normalize auth values consistently:
    - cast to str
    - strip whitespace/newlines
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return ""
    return value.strip()


def _read_shared_key_env() -> str:
    """
    LOCKED AUTH SOURCE (env-only):
    Licensing must read from os.environ["PPA_SHARED_KEY"].
    We mirror that exact semantic, but safely handle missing env by returning "".
    """
    try:
        return os.environ["PPA_SHARED_KEY"]
    except KeyError:
        return ""


def _get_shared_key() -> str:
    """
    Shared secret injected by the WP PHP controller server-side (X-PPA-Key).
    Reads from os.environ["PPA_SHARED_KEY"], not Django settings.
    """
    key = _norm(_read_shared_key_env())
    if not key:
        raise APIError(
            code="server_misconfig",
            message="Licensing not configured (PPA_SHARED_KEY missing).",
            http_status=500,
            err_type="server_error",
        )
    return key


def _shared_key_header_valid(request: HttpRequest) -> bool:
    """
    OPTION A SUPPORT (non-fatal shared-key check):

    Returns True ONLY if:
      - env shared key exists, AND
      - provided X-PPA-Key matches it (constant-time compare)

    IMPORTANT:
      - If missing/invalid, return False (do NOT raise 401),
        because license endpoints also support license_key + site_url auth now.
    """
    expected = _norm(_read_shared_key_env())
    if not expected:
        return False

    provided = request.headers.get("X-PPA-Key")
    if provided is None:
        provided = request.META.get("HTTP_X_PPA_KEY")
    provided = _norm(provided)
    if not provided:
        return False

    return bool(hmac.compare_digest(provided, expected))


def _require_shared_key(request: HttpRequest) -> None:
    """
    Strict shared-key enforcement (legacy behavior).
    Kept for any INTERNAL endpoints that still want strict server-to-server auth.
    License endpoints no longer call this under Option A.
    """
    expected = _get_shared_key()

    provided = request.headers.get("X-PPA-Key")
    if provided is None:
        provided = request.META.get("HTTP_X_PPA_KEY")
    provided = _norm(provided)

    if (not provided) or (not hmac.compare_digest(provided, expected)):
        raise APIError(
            code="unauthorized",
            message="Unauthorized.",
            http_status=401,
            err_type="auth_error",
        )


def _rate_limit_or_raise(*, scope: str, ip: str, license_key: Optional[str]) -> None:
    """
    Cache-based fixed window limiter:
    - per endpoint per IP
    - per endpoint per license_key (if provided)

    Fail-closed on cache errors (conservative for a licensing system).
    """
    window = int(timezone.now().timestamp() // RL_WINDOW_SECONDS)
    ip_key = f"ppa:rl:{scope}:ip:{ip}:{window}"
    lk = (license_key or "").strip()
    lic_key = f"ppa:rl:{scope}:key:{lk}:{window}" if lk else None

    try:
        ip_count = cache.get(ip_key)
        if ip_count is None:
            cache.set(ip_key, 1, timeout=RL_WINDOW_SECONDS + 5)
            ip_count = 1
        else:
            ip_count = int(ip_count) + 1
            cache.set(ip_key, ip_count, timeout=RL_WINDOW_SECONDS + 5)

        if ip_count > RL_IP_LIMIT_PER_WINDOW:
            raise APIError(
                code="rate_limited",
                message="Too many requests. Try again shortly.",
                http_status=429,
                err_type="rate_limit",
            )

        if lic_key:
            k_count = cache.get(lic_key)
            if k_count is None:
                cache.set(lic_key, 1, timeout=RL_WINDOW_SECONDS + 5)
                k_count = 1
            else:
                k_count = int(k_count) + 1
                cache.set(lic_key, k_count, timeout=RL_WINDOW_SECONDS + 5)

            if k_count > RL_KEY_LIMIT_PER_WINDOW:
                raise APIError(
                    code="rate_limited",
                    message="Too many requests for this license key. Try again shortly.",
                    http_status=429,
                    err_type="rate_limit",
                )

    except APIError:
        raise
    except Exception:
        raise APIError(
            code="rate_limit_unavailable",
            message="Licensing temporarily unavailable.",
            http_status=503,
            err_type="server_error",
        )


def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    """Parse request body JSON safely. We never log secrets."""
    raw = request.body or b""
    if not raw:
        raise APIError(code="missing_body", message="Missing JSON body.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise APIError(code="invalid_json", message="Invalid JSON.")
    if not isinstance(payload, dict):
        raise APIError(code="invalid_json", message="JSON root must be an object.")
    return payload


_LICENSE_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{10,128}$")


def _clean_license_key(value: Any) -> str:
    if not isinstance(value, str):
        raise APIError(code="invalid_license_key", message="license_key must be a string.")
    key = value.strip()
    if not _LICENSE_KEY_RE.match(key):
        raise APIError(code="invalid_license_key", message="license_key format invalid.")
    return key


def _normalize_site_url(value: Any) -> str:
    """
    Normalization rules (strict, deterministic):
    - require http(s)
    - lower-case host
    - drop path/query/fragment
    - drop trailing slash
    - keep port if present
    - return scheme://host[:port]
    """
    if not isinstance(value, str):
        raise APIError(code="invalid_site_url", message="site_url must be a string.")
    raw = value.strip()
    if not raw:
        raise APIError(code="invalid_site_url", message="site_url is required.")

    model_norm = getattr(Activation, "normalize_site_url", None)
    if callable(model_norm):
        normalized = model_norm(raw)
        if not isinstance(normalized, str) or not normalized.strip():
            raise APIError(code="invalid_site_url", message="site_url invalid.")
        return normalized.strip()

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise APIError(code="invalid_site_url", message="site_url must include http:// or https://")
    if not parsed.hostname:
        raise APIError(code="invalid_site_url", message="site_url hostname missing.")

    host = parsed.hostname.lower()
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}".rstrip("/")


def _get_license_or_raise(license_key: str) -> License:
    lic = License.objects.filter(key=license_key).first()
    if not lic:
        raise APIError(code="not_found", message="License not found.", http_status=404)
    return lic


def _ensure_license_active(lic: License) -> None:
    is_active = getattr(lic, "is_active", None)
    if callable(is_active):
        if not is_active():
            raise APIError(code="license_inactive", message="License is not active.", http_status=403)
        return

    status = getattr(lic, "status", "")
    if str(status) != "active":
        raise APIError(code="license_inactive", message="License is not active.", http_status=403)


def _activation_count_for_license(lic: License) -> int:
    return Activation.objects.filter(license=lic).count()


def _license_limit_allows_site(lic: License) -> bool:
    if bool(getattr(lic, "unlimited_sites", False)):
        return True
    max_sites = int(getattr(lic, "max_sites", 0) or 0)
    if max_sites <= 0:
        return False
    return _activation_count_for_license(lic) < max_sites


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def _touch_activation(act: Activation, *, force: bool = False) -> None:  # CHANGED:
    """
    Update last_verified_at.
    - force=True: always write (e.g., explicit activate call)
    - force=False: throttled to reduce DB churn and improve verify cacheability
    """
    now = timezone.now()
    last = getattr(act, "last_verified_at", None)
    if (not force) and last:
        try:
            age = (now - last).total_seconds()
            if age < VERIFY_TOUCH_MIN_SECONDS:
                return
        except Exception:
            # If datetime math fails for any reason, fail safe and write once.
            pass
    act.last_verified_at = now
    act.save(update_fields=["last_verified_at"])


def _getattr_int(obj: Any, *names: str) -> Optional[int]:  # CHANGED:
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v is None:
                continue
            try:
                return int(v)
            except Exception:
                continue
    return None


def _getattr_dt(obj: Any, *names: str):  # CHANGED:
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n)
            if v:
                return v
    return None


def _month_bounds(now_dt) -> Tuple[Any, Any]:  # CHANGED:
    """
    Fallback billing period: calendar month bounds.
    Use License-period fields if present; this is only a deterministic fallback.
    """
    start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # next month:
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _effective_entitlements(lic: License) -> Dict[str, Any]:  # CHANGED:
    """
    Determine effective entitlements using:
    1) explicit License fields if they exist
    2) fallback PLAN_DEFAULTS by plan_slug

    HARDEN RULE:
    - For AI-included plans, monthly token limit must never be 0 (0 == "unset" in early stages). # CHANGED:
    - For non-unlimited plans, max_sites must never be 0 (0 == "unset").                         # CHANGED:
    """
    slug = getattr(lic, "plan_slug", None) or "unknown"
    fallback = PLAN_DEFAULTS.get(str(slug), (0, False, 0, True, False))

    used_default_sites = False  # CHANGED:
    used_default_tokens = False  # CHANGED:

    # Feature flags first (needed to interpret "0 means unset")
    ai_included = bool(getattr(lic, "ai_included", fallback[3]))  # CHANGED:
    byo_required = bool(getattr(lic, "byo_key_required", fallback[4]))  # CHANGED:

    # Sites
    unlimited_sites = bool(getattr(lic, "unlimited_sites", fallback[1]))
    max_sites = _getattr_int(lic, "max_sites")
    if max_sites is None:
        max_sites = int(fallback[0])
        used_default_sites = True  # CHANGED:
    # If not unlimited, treat 0/neg as unset and fall back.
    if (not unlimited_sites) and (max_sites <= 0):  # CHANGED:
        max_sites = int(fallback[0])  # CHANGED:
        used_default_sites = True  # CHANGED:

    # Tokens (monthly included)
    monthly_limit = _getattr_int(
        lic,
        "monthly_token_limit",
        "monthly_tokens",
        "tokens_monthly",
        "token_limit_monthly",
        "included_tokens_monthly",
    )
    if monthly_limit is None:
        monthly_limit = int(fallback[2])
        used_default_tokens = True  # CHANGED:

    # CRITICAL: AI-included plans must not return 0 tokens unless you explicitly set them later.  # CHANGED:
    if ai_included and (not byo_required) and (int(monthly_limit) <= 0):  # CHANGED:
        monthly_limit = int(fallback[2])  # CHANGED:
        used_default_tokens = True  # CHANGED:

    # Source label (honest + useful for debugging without leaking secrets)
    if used_default_sites and used_default_tokens:  # CHANGED:
        source = "plan_defaults"  # CHANGED:
    elif used_default_sites or used_default_tokens:  # CHANGED:
        source = "mixed"  # CHANGED:
    else:
        source = "license_fields"

    return {
        "plan_slug": slug,
        "sites": {"max": int(max_sites), "unlimited": bool(unlimited_sites)},
        "tokens": {"monthly_limit": int(monthly_limit)},
        "features": {"ai_included": bool(ai_included), "byo_key_required": bool(byo_required)},
        "source": source,
    }


def _token_snapshot(lic: License) -> Dict[str, Any]:  # CHANGED:
    """
    Token accounting snapshot.

    Defensive + stable output shape.
    This will later be wired to real UsageEvent/Credit models without changing response shape.
    """
    now = timezone.now()

    # Prefer license-defined billing period if available.
    period_start = _getattr_dt(lic, "current_period_start", "period_start", "billing_period_start")
    period_end = _getattr_dt(lic, "current_period_end", "period_end", "billing_period_end")
    if not period_start or not period_end:
        period_start, period_end = _month_bounds(now)

    ent = _effective_entitlements(lic)
    monthly_limit = int(ent["tokens"]["monthly_limit"] or 0)

    monthly_used = _getattr_int(
        lic,
        "monthly_tokens_used",
        "tokens_used_this_period",
        "tokens_used_current_period",
        "tokens_used_month",
    )
    if monthly_used is None:
        monthly_used = 0

    purchased_balance = _getattr_int(
        lic,
        "purchased_tokens_balance",
        "tokens_purchased_balance",
        "addon_tokens_balance",
        "tokens_addon_balance",
        "extra_tokens_balance",
    )
    if purchased_balance is None:
        purchased_balance = 0

    monthly_remaining = max(0, monthly_limit - int(monthly_used))
    remaining_total = monthly_remaining + max(0, int(purchased_balance))

    return {
        "period": {"start": period_start, "end": period_end},
        "monthly_limit": monthly_limit,
        "monthly_used": int(monthly_used),
        "monthly_remaining": int(monthly_remaining),
        "purchased_balance": int(purchased_balance),
        "remaining_total": int(remaining_total),
    }


# ------------------------------
# Endpoints
# ------------------------------
@csrf_exempt
@require_POST
def license_activate(request: HttpRequest) -> JsonResponse:
    """
    Activate a site for a license key.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Auth (Option A):
      - If X-PPA-Key matches env PPA_SHARED_KEY -> allowed (internal/proxy path)
      - Otherwise -> allowed via license_key + site_url (customer path)

    Output:
      ok + activation state (display-only; Django remains the source of truth)
    """
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="activate", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        _ensure_license_active(lic)

        act = Activation.objects.filter(license=lic, site_url=site_url).first()
        if act:
            _touch_activation(act, force=True)  # explicit action -> write
            return _json_ok(
                {
                    "license": {
                        "key_masked": _mask_key(license_key),
                        "plan_slug": getattr(lic, "plan_slug", None),
                        "status": getattr(lic, "status", None),
                        "max_sites": getattr(lic, "max_sites", None),
                        "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),
                        "byo_key_required": bool(getattr(lic, "byo_key_required", False)),
                        "ai_included": bool(getattr(lic, "ai_included", False)),
                        "expires_at": getattr(lic, "expires_at", None),
                    },
                    "activation": {
                        "site_url": site_url,
                        "activated": True,
                        "activated_at": getattr(act, "activated_at", None),
                        "last_verified_at": getattr(act, "last_verified_at", None),
                        "already_active": True,
                    },
                }
            )

        if not _license_limit_allows_site(lic):
            raise APIError(
                code="site_limit_reached",
                message="Site activation limit reached for this plan.",
                http_status=403,
                err_type="plan_limit",
            )

        now = timezone.now()
        act = Activation.objects.create(
            license=lic,
            site_url=site_url,
            activated_at=now,
            last_verified_at=now,
        )

        return _json_ok(
            {
                "license": {
                    "key_masked": _mask_key(license_key),
                    "plan_slug": getattr(lic, "plan_slug", None),
                    "status": getattr(lic, "status", None),
                    "max_sites": getattr(lic, "max_sites", None),
                    "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),
                    "byo_key_required": bool(getattr(lic, "byo_key_required", False)),
                    "ai_included": bool(getattr(lic, "ai_included", False)),
                    "expires_at": getattr(lic, "expires_at", None),
                },
                "activation": {
                    "site_url": site_url,
                    "activated": True,
                    "activated_at": getattr(act, "activated_at", None),
                    "last_verified_at": getattr(act, "last_verified_at", None),
                    "already_active": False,
                },
            }
        )

    except APIError as e:
        return _json_err(e)


@csrf_exempt
@require_POST
def license_verify(request: HttpRequest) -> JsonResponse:
    """
    Verify a license + site activation.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Auth (Option A):
      - If X-PPA-Key matches env PPA_SHARED_KEY -> allowed (internal/proxy path)
      - Otherwise -> allowed via license_key + site_url (customer path)

    Output:
      ok true if license active AND activation exists.
      Includes deterministic license status (sites + tokens + features) for WP Settings display.
    """
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="verify", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        _ensure_license_active(lic)

        act = Activation.objects.filter(license=lic, site_url=site_url).first()
        if not act:
            raise APIError(
                code="not_activated",
                message="This site is not activated for this license.",
                http_status=403,
                err_type="activation",
            )

        _touch_activation(act, force=False)  # throttled writes for cacheability

        ent = _effective_entitlements(lic)
        sites_used = _activation_count_for_license(lic)
        tokens = _token_snapshot(lic)

        data = {
            "cache_ttl_seconds": VERIFY_CACHE_TTL_SECONDS,
            "server_time": timezone.now(),
            "license": {
                # Backward-safe fields (existing keys kept)
                "key_masked": _mask_key(license_key),
                "plan_slug": getattr(lic, "plan_slug", None),
                "status": getattr(lic, "status", None),
                "max_sites": getattr(lic, "max_sites", None),
                "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),
                "byo_key_required": bool(getattr(lic, "byo_key_required", False)),
                "ai_included": bool(getattr(lic, "ai_included", False)),
                "expires_at": getattr(lic, "expires_at", None),
                # Deterministic snapshots
                "sites": {
                    "used": int(sites_used),
                    "max": int(ent["sites"]["max"]),
                    "unlimited": bool(ent["sites"]["unlimited"]),
                },
                "features": {
                    "ai_included": bool(ent["features"]["ai_included"]),
                    "byo_key_required": bool(ent["features"]["byo_key_required"]),
                },
                "tokens": tokens,
                "entitlements_source": ent.get("source"),
            },
            "activation": {
                "site_url": site_url,
                "activated": True,
                "activated_at": getattr(act, "activated_at", None),
                "last_verified_at": getattr(act, "last_verified_at", None),
            },
        }

        resp = _json_ok(data)
        resp["Cache-Control"] = f"private, max-age={VERIFY_CACHE_TTL_SECONDS}"
        return resp

    except APIError as e:
        return _json_err(e)


@csrf_exempt
@require_POST
def license_deactivate(request: HttpRequest) -> JsonResponse:
    """
    Deactivate a site for a license.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Auth (Option A):
      - If X-PPA-Key matches env PPA_SHARED_KEY -> allowed (internal/proxy path)
      - Otherwise -> allowed via license_key + site_url (customer path)

    Output:
      ok true (idempotent)
    """
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="deactivate", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        # Deactivate is cleanup-safe; we do NOT require active status.
        deleted, _ = Activation.objects.filter(license=lic, site_url=site_url).delete()

        return _json_ok(
            {
                "license": {
                    "key_masked": _mask_key(license_key),
                    "plan_slug": getattr(lic, "plan_slug", None),
                    "status": getattr(lic, "status", None),
                },
                "activation": {
                    "site_url": site_url,
                    "deactivated": True,
                    "deleted": int(deleted),
                },
            }
        )

    except APIError as e:
        return _json_err(e)
