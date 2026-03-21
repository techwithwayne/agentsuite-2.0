# /home/techwithwayne/agentsuite/postpress_ai/views/license.py
# postpress_ai.views.license

"""
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
# 2026-01-25: HARDEN: On verify errors (inactive/not_activated), still return deterministic contract in data
#            so WP can display Plan/Sites/Tokens without guessing.                                         # CHANGED:
# 2026-01-25: HARDEN: Activate/Deactivate now also return the same deterministic contract snapshot.         # CHANGED:
# 2026-01-25: ADD: tokens.mode ("included"|"byo"|"none") to make plan behavior explicit for WP.             # CHANGED:
# 2026-01-25: HARDEN: Unknown plan slugs now default to conservative entitlements (BYO required, no included tokens).
# 2026-01-25: ADD: plan.name + plan.label + links{} added to the deterministic license contract snapshot for upcoming Account UI.
# 2026-01-25: ADD: sites.remaining + tokens.remaining_total exported at top-level snapshots (WP never has to compute).
# 2026-01-25: HARDEN: activate/deactivate errors now include deterministic contract payload when possible (better WP UX).
# 2026-01-25: HARDEN: verify error responses also emit Cache-Control for deterministic caching behavior.
# 2026-01-25: HARDEN: Account links now support per-plan env overrides and strict URL validation (fail-closed). # CHANGED:
# 2026-01-26: FIX: Token usage in license.v1 now prefers SUM(UsageEvent.total_tokens) for the current period. # CHANGED:
#            - Solves “0 used” in WP when License legacy counters are unset/stale.                           # CHANGED:
#            - Field/relationship detection is introspective + fail-safe (never breaks licensing).          # CHANGED:
#            - Transitional safety: monthly_used = max(legacy_field_used, usage_event_sum).                 # CHANGED:
# 2026-01-26: FIX: _effective_entitlements now respects PLAN_DEFAULTS for boolean flags unless explicit overrides exist. # CHANGED:
#            - Prevents agency_byo showing max=0 + unlimited=False when DB booleans default False/True.               # CHANGED:
#            - Keeps license.v1 response shape unchanged; only corrects computed entitlements.                         # CHANGED:
# 2026-02-22: FIX: Include full activated sites list in license.v1 at license.sites.list (WP Account needs it). # CHANGED:
# 2026-02-23: FIX: CSRF-exempt + POST-only /license/deactivate/ so WP server-to-server calls never 403. # CHANGED:

# 2026-03-01: WIRE: tokens.purchased_balance now derives from CreditLedger (pack_grant/manual_adjust/spend) scoped to license. # CHANGED:

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from django.core.cache import cache
from django.apps import apps  # CHANGED:
from django.db import IntegrityError, models, transaction  # CHANGED:
from django.db.models import Sum, Q  # CHANGED:
from django.db.models.functions import Coalesce  # CHANGED:
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from postpress_ai.plugin_updates import plugin_update_snapshot

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
# Campaign issuance (trial)
# ------------------------------
TRIAL_CAMPAIGN_SLUG = "trial_25k_14d"  # CHANGED:
TRIAL_TOKENS_GRANTED = 25_000  # CHANGED:
TRIAL_DURATION_DAYS = 14  # CHANGED:

# ------------------------------
# Plan defaults (fallback only)
# Django remains authoritative; if License has explicit fields set, those win.
# ------------------------------
PLAN_DEFAULTS = {  # CHANGED:
    # slug: (max_sites, unlimited, monthly_tokens, ai_included, byo_required)
    "tyler": (3, False, 120_000, True, False),  # CHANGED: early bird aligned to "creator" class tokens
    "solo": (1, False, 200_000, True, False),
    "creator": (3, False, 500_000, True, False),
    "studio": (10, False, 1_500_000, True, False),
    "agency": (25, False, 4_000_000, True, False),
    "agency_byo": (0, True, 0, False, True),  # Unlimited sites, BYO key, no included tokens
    # Campaign trial (expires in 14 days, uses purchased_balance via ledger grant)  # CHANGED:
    "trial_25k_14d": (1, False, 0, True, False),  # CHANGED:
}


# ------------------------------
# Plan metadata (display-only)
# ------------------------------
# CHANGED:
# - PLAN_DEFAULTS is strictly a fallback.
# - Unknown plan slugs MUST fail closed (conservative) unless explicit License fields exist.
# - WP UI can display plan names without guessing.
PLAN_META = {  # CHANGED:
    "tyler": {"name": "Tyler Early Bird", "label": "Early Bird"},
    "solo": {"name": "Solo", "label": "Solo"},
    "creator": {"name": "Creator", "label": "Creator"},
    "studio": {"name": "Studio", "label": "Studio"},
    "agency": {"name": "Agency", "label": "Agency"},
    "agency_byo": {"name": "Agency (BYO Key)", "label": "Agency BYO"},
    "trial_25k_14d": {"name": "Trial 25,000 Tokens (14 Days)", "label": "Trial"},  # CHANGED:
}


# slug: (max_sites, unlimited, monthly_tokens, ai_included, byo_required)
UNKNOWN_PLAN_FALLBACK = (0, False, 0, False, True)  # CHANGED: fail closed (BYO required, no included tokens)


def _clean_plan_slug(value: Any) -> str:  # CHANGED:
    """Normalize plan slug for map lookups without changing DB values."""
    if value is None:
        return "unknown"
    try:
        s = str(value).strip().lower()
    except Exception:
        return "unknown"
    # common separators to underscore
    s = s.replace("-", "_")
    return s or "unknown"


def _plan_meta(slug: str) -> Dict[str, str]:  # CHANGED:
    s = _clean_plan_slug(slug)
    meta = PLAN_META.get(s)
    if meta:
        return {"slug": s, "name": meta.get("name") or s, "label": meta.get("label") or meta.get("name") or s}
    # Unknown plan: safe display values (does not imply entitlements)
    return {"slug": s, "name": s, "label": s}


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
# ------------------------------
# Helpers
# ------------------------------
def _resp_meta(http_status: int, *, error_code: Optional[str] = None, error_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Response metadata (stable, WP-friendly, support-friendly).
    - Always present.
    - Does NOT include per-request unique data (keeps verify/cache behavior sane).
    """
    meta: Dict[str, Any] = {"http_status": int(http_status)}
    if error_code:
        meta["error_code"] = str(error_code)
    if error_type:
        meta["error_type"] = str(error_type)
    return meta


def _json_ok(data: Dict[str, Any], status: int = 200) -> JsonResponse:
    return JsonResponse(
        {"ok": True, "data": data, "meta": _resp_meta(status), "ver": API_VER},
        status=status,
    )


def _json_err(e: APIError, data: Optional[Dict[str, Any]] = None) -> JsonResponse:
    """
    Error response helper.

    Optionally include a deterministic `data` payload even on errors.
    This is critical for WP admin UX: Plan/Sites/Tokens can still render when
    a license is inactive or a site is not activated.
    """
    payload: Dict[str, Any] = {
        "ok": False,
        "error": {
            "type": e.err_type,
            "code": e.code,
            "message": e.message,
        },
        "meta": _resp_meta(e.http_status, error_code=e.code, error_type=e.err_type),
        "ver": API_VER,
    }
    if isinstance(data, dict):
        payload["data"] = data
    return JsonResponse(payload, status=e.http_status)

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
    """
    Strict active check.

    Supports both:
      - is_active as a method (legacy)
      - is_active as a boolean property (current License model)

    Also enforces expires_at when available.
    """
    attr = getattr(lic, "is_active", None)

    # Legacy: method form
    if callable(attr):
        if not bool(attr()):
            raise APIError(code="license_inactive", message="License is not active.", http_status=403)
        return

    # Current: property form
    if attr is not None:
        if not bool(attr):
            raise APIError(code="license_inactive", message="License is not active.", http_status=403)
        return

    # Fallback: status + expires_at
    status = getattr(lic, "status", "")
    if str(status) != "active":
        raise APIError(code="license_inactive", message="License is not active.", http_status=403)

    expires_at = getattr(lic, "expires_at", None)
    if expires_at and timezone.now() > expires_at:
        raise APIError(code="license_inactive", message="License is not active.", http_status=403)



def _activation_count_for_license(lic: License) -> int:
    return Activation.objects.filter(license=lic).count()


def _sites_list_for_license(lic: License, *, limit: int = 50) -> list:  # CHANGED:
    """
    Return a list of activated sites for this license.

    This is intentionally display-focused (WP Account screen).
    - Uses Activation rows for this license
    - Orders by recent activity
    - De-dupes exact URLs only (http vs https remain distinct if present in DB)
    - Caps output for payload safety
    - Never breaks licensing: returns [] on any exception
    """
    try:
        qs = (
            Activation.objects.filter(license=lic)
            .order_by("-last_verified_at", "-activated_at", "-id")
        )

        rows = []
        seen = set()

        # small overscan lets us dedupe without accidentally returning < limit
        overscan = max(limit * 2, limit)

        for act in qs[:overscan]:
            url = getattr(act, "site_url", None)
            url = str(url).strip() if url is not None else ""
            if not url:
                continue

            # Deduplicate exact URL string (case-insensitive, trailing-slash-insensitive).
            key = url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "url": url,
                    "status": "activated",
                    "activated_at": getattr(act, "activated_at", None),
                    "last_verified_at": getattr(act, "last_verified_at", None),
                }
            )

            if len(rows) >= limit:
                break

        return rows
    except Exception:
        return []
    
def _billing_email_for_license(lic: License) -> str:
    """
    Key-connected email = Entitlement.customer.email (best-effort).
    Never breaks licensing: returns "" on any exception / missing rows.
    """
    try:
        Entitlement = apps.get_model("postpress_ai", "Entitlement")
        qs = (
            Entitlement.objects.filter(license=lic)
            .select_related("customer")
            .order_by("-id")
        )
        ent = qs.first()
        cust = getattr(ent, "customer", None) if ent else None
        email = getattr(cust, "email", "") or ""
        return str(email).strip()
    except Exception:
        return ""


def _license_limit_allows_site(lic, site_url: str = "") -> bool:
    """
    PostPress AI — Site activation limit check

    ========= CHANGE LOG =========
    2026-01-26: FIX: Enforce site limits using _effective_entitlements(lic) (PLAN_DEFAULTS fallback)
               instead of raw License.max_sites/unlimited_sites.  # CHANGED:
    """

    # --- Normalize site URL (idempotency + stable comparisons) ---
    def _norm(u: str) -> str:
        u = (u or "").strip().lower()
        while u.endswith("/"):
            u = u[:-1]
        return u

    site_url_n = _norm(site_url)

    # --- Pull effective entitlements (this is the critical fix) ---
    ent = _effective_entitlements(lic) or {}

    # Support both possible shapes:
    # A) {"sites": {"max": X, "unlimited": bool, ...}, ...}
    # B) {"max_sites": X, "unlimited_sites": bool, ...}
    sites_ent = ent.get("sites") if isinstance(ent.get("sites"), dict) else {}

    unlimited = bool(
        ent.get("unlimited_sites")
        or sites_ent.get("unlimited")
    )

    if unlimited:
        return True

    max_sites = (
        sites_ent.get("max")
        if sites_ent.get("max") is not None
        else ent.get("max_sites")
    )

    try:
        max_sites_int = int(max_sites or 0)
    except Exception:
        max_sites_int = 0

    # Defensive: if entitlements say "0", treat as no capacity.
    if max_sites_int <= 0:
        return False

    # --- Activation counting (tries to be compatible with your model field names) ---
    # If the same site is already active, allow (idempotent activate).
    try:
        from postpress_ai.models import Activation  # adjust if your import path differs

        qs = Activation.objects.filter(license=lic)

        # "active" filter variants
        field_names = {f.name for f in Activation._meta.get_fields() if hasattr(f, "name")}

        if "is_active" in field_names:
            qs_active = qs.filter(is_active=True)
        elif "active" in field_names:
            qs_active = qs.filter(active=True)
        elif "status" in field_names:
            qs_active = qs.filter(status__in=["active", "activated"])
        elif "deactivated_at" in field_names:
            qs_active = qs.filter(deactivated_at__isnull=True)
        else:
            qs_active = qs  # fallback: count all rows

        # Idempotent check: if this site already exists as active, allow
        if site_url_n:
            if "site_url" in field_names:
                if qs_active.filter(site_url__iexact=site_url_n).exists():
                    return True
            elif "site" in field_names:
                # rare alt naming
                if qs_active.filter(site__iexact=site_url_n).exists():
                    return True

        used = qs_active.count()

    except Exception:
        # If we cannot evaluate activations for any reason, fail closed (server-side strict)
        return False

    return used < max_sites_int


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
    1) explicit License fields (when truly set/overridden)
    2) fallback PLAN_DEFAULTS by plan_slug

    HARDEN RULES:
    - For AI-included plans, monthly token limit must never be 0 (0 == "unset" early on). # CHANGED:
    - For non-unlimited plans, max_sites must never be 0 (0 == "unset").                   # CHANGED:
    - Boolean flags (unlimited_sites / ai_included / byo_key_required) default to model values
      that may not represent the plan. We therefore treat booleans as "override-only" unless
      there is a corresponding explicit override signal (e.g., max_sites set, monthly_token_limit set). # CHANGED:
      This fixes BYO plans showing 0 sites + not unlimited when DB boolean defaults are False.           # CHANGED:
    """
    slug_raw = getattr(lic, "plan_slug", None)  # CHANGED:
    slug = _clean_plan_slug(slug_raw)  # CHANGED:
    fallback = PLAN_DEFAULTS.get(str(slug), UNKNOWN_PLAN_FALLBACK)  # CHANGED:

    used_default_sites = False  # CHANGED:
    used_default_tokens = False  # CHANGED:

    # --- Sites overrides ---
    # If max_sites is NULL/None in DB, we treat it as "no override" and rely on plan defaults.  # CHANGED:
    max_sites = _getattr_int(lic, "max_sites")  # CHANGED:
    has_sites_override = max_sites is not None  # CHANGED:

    # Unlimited sites: treat True as an explicit override; treat False as "no override" unless max_sites is set.  # CHANGED:
    lic_unlimited_raw = getattr(lic, "unlimited_sites", None)  # CHANGED:
    if bool(lic_unlimited_raw):  # CHANGED:
        unlimited_sites = True  # CHANGED:
        has_sites_override = True  # CHANGED:
    elif has_sites_override:  # CHANGED:
        unlimited_sites = False  # CHANGED:
    else:  # CHANGED:
        unlimited_sites = bool(fallback[1])  # CHANGED:

    if max_sites is None:  # CHANGED:
        max_sites = int(fallback[0])  # CHANGED:
        used_default_sites = True  # CHANGED:
    # If not unlimited, treat 0/neg as unset and fall back.  # CHANGED:
    if (not unlimited_sites) and (int(max_sites) <= 0):  # CHANGED:
        max_sites = int(fallback[0])  # CHANGED:
        used_default_sites = True  # CHANGED:

    # --- Token overrides ---
    monthly_limit = _getattr_int(  # CHANGED:
        lic,
        "monthly_token_limit",
        "monthly_tokens",
        "tokens_monthly",
        "token_limit_monthly",
        "included_tokens_monthly",
    )
    has_tokens_override = monthly_limit is not None  # CHANGED:
    if monthly_limit is None:  # CHANGED:
        monthly_limit = int(fallback[2])  # CHANGED:
        used_default_tokens = True  # CHANGED:

    # Feature flags:
    # Only treat ai_included/byo_key_required as explicit overrides when tokens are explicitly overridden. # CHANGED:
    if has_tokens_override:  # CHANGED:
        ai_included = bool(getattr(lic, "ai_included", fallback[3]))  # CHANGED:
        byo_required = bool(getattr(lic, "byo_key_required", fallback[4]))  # CHANGED:
    else:  # CHANGED:
        ai_included = bool(fallback[3])  # CHANGED:
        byo_required = bool(fallback[4])  # CHANGED:

    # CRITICAL: AI-included plans must not return 0 tokens unless explicitly set later.  # CHANGED:
    if ai_included and (not byo_required) and (int(monthly_limit) <= 0):  # CHANGED:
        monthly_limit = int(fallback[2])  # CHANGED:
        used_default_tokens = True  # CHANGED:

    # Source label (honest + useful for debugging without leaking secrets)  # CHANGED:
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


def _usageevent_sum_tokens_for_period(lic: License, period_start, period_end) -> Optional[int]:  # CHANGED:
    """
    Best-effort SUM(UsageEvent.total_tokens) for this license within [period_start, period_end).

    Bulletproof constraints:
    - No assumptions about field names: we introspect UsageEvent model fields.
    - Works whether UsageEvent has FK to License OR a license_key string.
    - If anything is missing/misconfigured, returns None (never breaks licensing).
    """  # CHANGED:
    try:
        from postpress_ai.models.usage_event import UsageEvent  # local import prevents import-time coupling
    except Exception:
        return None

    try:
        fields = [f for f in UsageEvent._meta.get_fields() if hasattr(f, "name")]
        field_names = {f.name for f in fields}
    except Exception:
        return None

    # 1) License relationship (preferred)
    license_fk_field: Optional[str] = None
    try:
        for f in fields:
            # many_to_one covers ForeignKey; one_to_one is acceptable too.
            if getattr(f, "is_relation", False) and getattr(f, "related_model", None) is License:
                if bool(getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
                    license_fk_field = f.name
                    break
    except Exception:
        license_fk_field = None

    # 2) License key string fallback
    license_key_field: Optional[str] = None
    if not license_fk_field:
        for cand in ("license_key", "lic_key", "licensekey", "key"):
            if cand in field_names:
                license_key_field = cand
                break

    # 3) Timestamp field candidates
    ts_field: Optional[str] = None
    for cand in (
        "created_at",
        "occurred_at",
        "event_at",
        "timestamp",
        "ts",
        "created",
        "at",
        "time",
    ):
        if cand in field_names:
            ts_field = cand
            break

    # 4) Total token field candidates
    total_field: Optional[str] = None
    for cand in ("total_tokens", "tokens_total", "token_total", "tokens", "total"):
        if cand in field_names:
            total_field = cand
            break

    if not ts_field or not total_field:
        return None

    qs = UsageEvent.objects.all()

    if license_fk_field:
        qs = qs.filter(**{license_fk_field: lic})
    elif license_key_field:
        lk = getattr(lic, "key", None)
        if not lk:
            return None
        qs = qs.filter(**{license_key_field: str(lk)})
    else:
        return None

    qs = qs.filter(**{f"{ts_field}__gte": period_start, f"{ts_field}__lt": period_end})

    try:
        agg = qs.aggregate(total=Coalesce(Sum(total_field), 0))
        val = agg.get("total")
        return int(val or 0)
    except Exception:
        return None



def _creditledger_purchased_balance_for_license(lic: License) -> Optional[int]:  # CHANGED:
    """
    Best-effort purchased token balance from CreditLedger for THIS license.

    Definition (locked for WP contract):
    - Purchased tokens are ledger-based and are ALWAYS separate from plan monthly tokens.
    - purchased_balance = SUM(amount) for entry_type in {pack_grant, manual_adjust, spend}
      scoped to this license.
    - Monthly grants are excluded by design.

    Notes:
    - CreditLedger.amount is defined as: Positive = add credits, Negative = spend credits.
    - Never breaks licensing: returns None if the credit models aren't available or any query fails.
    """
    try:
        from postpress_ai.models.credit import CreditLedger  # local import avoids hard coupling
    except Exception:
        return None

    try:
        # Prefer model constants when present.
        t_pack = getattr(CreditLedger, "TYPE_PACK_GRANT", "pack_grant")
        t_spend = getattr(CreditLedger, "TYPE_SPEND", "spend")
        # In credit.py this constant is TYPE_MANUAL, not TYPE_MANUAL_ADJUST.
        t_manual = getattr(CreditLedger, "TYPE_MANUAL", "manual_adjust")

        types = [t_pack, t_manual, t_spend]

        # Prefer license linkage; also include legacy rows linked via credit_pack.  # CHANGED:
        qs = CreditLedger.objects.filter(entry_type__in=types).filter(Q(license=lic) | Q(credit_pack__license=lic))  # type: ignore  # CHANGED:

        agg = qs.aggregate(total=Coalesce(Sum("amount"), 0))
        val = agg.get("total")
        try:
            return max(0, int(val or 0))
        except Exception:
            return None
    except Exception:
        return None


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

    legacy_monthly_used = _getattr_int(  # CHANGED:
        lic,
        "monthly_tokens_used",
        "tokens_used_this_period",
        "tokens_used_current_period",
        "tokens_used_month",
    )
    if legacy_monthly_used is None:
        legacy_monthly_used = 0

    # CHANGED: Prefer UsageEvent sum for truth (but never let usage go backwards).
    usage_event_used = _usageevent_sum_tokens_for_period(lic, period_start, period_end)  # CHANGED:
    if usage_event_used is None:  # CHANGED:
        monthly_used = int(legacy_monthly_used)  # CHANGED:
    else:
        monthly_used = max(int(legacy_monthly_used), int(usage_event_used))  # CHANGED:

    # Legacy field fallback (kept for safety, but CreditLedger is authoritative when present).  # CHANGED:
    purchased_balance_legacy = _getattr_int(
        lic,
        "purchased_tokens_balance",
        "tokens_purchased_balance",
        "addon_tokens_balance",
        "tokens_addon_balance",
        "extra_tokens_balance",
    )
    if purchased_balance_legacy is None:
        purchased_balance_legacy = 0

    # CHANGED: Prefer CreditLedger (token pack purchases attach to the same activation key/license).  # CHANGED:
    purchased_balance_ledger = _creditledger_purchased_balance_for_license(lic)  # CHANGED:
    if purchased_balance_ledger is None:
        purchased_balance = int(purchased_balance_legacy)  # CHANGED:
    else:
        # Never let purchased balance go backwards if a legacy counter exists.  # CHANGED:
        purchased_balance = max(int(purchased_balance_legacy), int(purchased_balance_ledger))  # CHANGED:
        purchased_balance = max(0, int(purchased_balance))  # CHANGED:

    monthly_remaining = max(0, monthly_limit - int(monthly_used))
    remaining_total = monthly_remaining + max(0, int(purchased_balance))

    # CHANGED: Make the plan behavior explicit for WP (no guessing later).
    if bool(ent["features"]["byo_key_required"]):
        mode = "byo"
    elif bool(ent["features"]["ai_included"]):
        mode = "included"
    else:
        mode = "none"

    return {
        "mode": mode,  # CHANGED:
        "period": {"start": period_start, "end": period_end},
        "monthly_limit": monthly_limit,
        "monthly_used": int(monthly_used),
        "monthly_remaining": int(monthly_remaining),
        "purchased_balance": int(purchased_balance),
        "remaining_total": int(remaining_total),
    }


def _opt_str(value: Any) -> Optional[str]:  # CHANGED:
    """Return a safe stripped string or None."""
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return None
    value = value.strip()
    return value or None


def _safe_account_url(value: Optional[str]) -> Optional[str]:  # CHANGED:
    """
    Fail-closed URL validation for anything we send to WP as a clickable link.

    Rules:
    - Must be absolute http(s) URL with a hostname.
    - Production-safe default: require https unless it's clearly local/dev.
    - Reject whitespace, overly long values, and malformed URLs.

    CHANGED:
    - Never allow Stripe Billing Portal login URLs (email-login flow).
      The ONLY Stripe URL WP should ever receive is a one-time /p/session/... URL,
      minted on-demand during /license/verify/?intent=billing_portal&portal_session=1.
    """
    s = _opt_str(value)
    if not s:
        return None
    if any(ch.isspace() for ch in s):
        return None
    if len(s) > 2048:
        return None
    try:
        p = urlparse(s)
    except Exception:
        return None
    if p.scheme not in ("http", "https"):
        return None
    if not p.hostname:
        return None

    host = (p.hostname or "").lower()

    # CHANGED: block Stripe Billing Portal login URLs entirely here.
    if host == "billing.stripe.com":
        return None

    if p.scheme == "http":
        # Allow http ONLY for local/dev style hosts. Fail closed otherwise.  # CHANGED:
        if host not in ("localhost", "127.0.0.1") and (not host.endswith(".local")):
            return None

    return s


def _safe_stripe_billing_portal_session_url(value: Optional[str]) -> Optional[str]:  # CHANGED:
    """
    Strict validator for Stripe one-time Billing Portal session URLs.

    REQUIREMENTS (LOCKED):
    - Must be: https://billing.stripe.com/p/session/...
    - Must NOT be: /p/login (email-login flow)
    - Must be HTTPS and contain no whitespace
    """
    s = _opt_str(value)
    if not s:
        return None
    if any(ch.isspace() for ch in s):
        return None
    if len(s) > 2048:
        return None
    if not s.startswith("https://billing.stripe.com/p/session/"):
        return None
    return s


def _env_plan_url(base_key: str, plan_slug: str) -> Optional[str]:  # CHANGED:
    """
    Plan-aware env lookup:
      - PPA_UPGRADE_URL_TYLER
      - PPA_BUY_TOKENS_URL_CREATOR
      - PPA_BILLING_PORTAL_URL_AGENCY
    Fallback to the base key:
      - PPA_UPGRADE_URL
      - PPA_BUY_TOKENS_URL
      - PPA_BILLING_PORTAL_URL
    """
    slug = _clean_plan_slug(plan_slug).upper()
    slug = re.sub(r"[^A-Z0-9_]", "_", slug)  # belt + suspenders; should already be safe
    v = _opt_str(os.environ.get(f"{base_key}_{slug}"))
    if v:
        return v
    return _opt_str(os.environ.get(base_key))


def _account_links(lic: License, ent: Dict[str, Any], tokens: Dict[str, Any]) -> Dict[str, Optional[str]]:  # CHANGED:
    """
    Account / upgrade links for WP UI.

    LOCKED:
    - WP must never talk to Stripe.
    - Django may emit links to your own marketing/upgrade pages (which may later lead to Stripe),
      but WP only displays links returned by Django.

    Behavior (bulletproof defaults):
    - Prefer explicit License fields if present (authoritative).
    - Else, allow env configuration (optionally plan-specific).
    - Validate URLs strictly; invalid -> None (fail closed).
    - BYO plans: buy_tokens defaults to None unless explicitly set on the License.  # CHANGED:
    """
    plan_slug = ent.get("plan_slug") or "unknown"  # CHANGED:

    # Prefer explicit License fields if present (authoritative).
    upgrade = _opt_str(getattr(lic, "upgrade_url", None))
    buy_tokens = _opt_str(getattr(lic, "buy_tokens_url", None))
    billing_portal = _opt_str(getattr(lic, "billing_portal_url", None))

    # If not present on License, fall back to env (optionally per-plan).  # CHANGED:
    if not upgrade:
        upgrade = _env_plan_url("PPA_UPGRADE_URL", str(plan_slug))  # CHANGED:
    if not buy_tokens:
        buy_tokens = _env_plan_url("PPA_BUY_TOKENS_URL", str(plan_slug))  # CHANGED:
    if not billing_portal:
        billing_portal = _env_plan_url("PPA_BILLING_PORTAL_URL", str(plan_slug))  # CHANGED:

    # Default gating: BYO required => no token purchase link unless explicitly set on License.  # CHANGED:
    byo_required = bool(ent.get("features", {}).get("byo_key_required"))  # CHANGED:
    if byo_required and (not _opt_str(getattr(lic, "buy_tokens_url", None))):  # CHANGED:
        buy_tokens = None  # CHANGED:

    # Validate URLs strictly (fail closed).  # CHANGED:
    return {
        "upgrade": _safe_account_url(upgrade),  # CHANGED:
        "buy_tokens": _safe_account_url(buy_tokens),  # CHANGED:
        "billing_portal": _safe_account_url(billing_portal),  # CHANGED:
    }


def _license_contract_snapshot(license_key: str, lic: License) -> Dict[str, Any]:  # CHANGED:
    """
    Build a deterministic license contract snapshot for WP UI.

    Used by verify/activate/deactivate to keep responses consistent across actions.

    CHANGED:
    - Adds plan.name + plan.label for UI.
    - Adds sites.remaining and tokens.remaining_total (WP doesn't compute).
    - Adds links{} for upcoming Account screen (safe, non-Stripe).
    - Adds sites.list (activated sites list) for WP Account Sites card.  # CHANGED:
    """
    ent = _effective_entitlements(lic)
    plan = _plan_meta(ent.get("plan_slug"))  # CHANGED:
    sites_used = _activation_count_for_license(lic)
    sites_list = _sites_list_for_license(lic, limit=50)  # CHANGED:
    tokens = _token_snapshot(lic)
    billing_email = _billing_email_for_license(lic)
    links = _account_links(lic, ent, tokens)  # CHANGED:

    max_sites = int(ent["sites"]["max"])
    unlimited_sites = bool(ent["sites"]["unlimited"])
    sites_remaining = None if unlimited_sites else max(0, max_sites - int(sites_used))  # CHANGED:

    # Export a couple of computed token fields at top-level for WP convenience.  # CHANGED:
    tokens_monthly_remaining = int(tokens.get("monthly_remaining") or 0)
    tokens_remaining_total = int(tokens.get("remaining_total") or 0)

    return {
        # Identity (masked)
        "key_masked": _mask_key(license_key),

        # Plan (display)
        "plan_slug": plan.get("slug"),  # CHANGED: normalized slug for stable UI keys
        "plan": plan,  # CHANGED: {slug,name,label}
        "billing_email": billing_email or "",

        # Status
        "status": getattr(lic, "status", None),
        "expires_at": getattr(lic, "expires_at", None),

        # Backward-safe top-level fields (deterministic)
        "max_sites": max_sites,
        "unlimited_sites": unlimited_sites,
        "sites_used": int(sites_used),  # CHANGED:
        "sites_remaining": sites_remaining,  # CHANGED:

        "byo_key_required": bool(ent["features"]["byo_key_required"]),
        "ai_included": bool(ent["features"]["ai_included"]),

        # Deterministic snapshots (WP Settings + Account can parse these)
        "sites": {
            "used": int(sites_used),
            "max": max_sites,
            "unlimited": unlimited_sites,
            "remaining": sites_remaining,  # CHANGED:
            "list": sites_list,  # CHANGED:
        },
        "features": {
            "ai_included": bool(ent["features"]["ai_included"]),
            "byo_key_required": bool(ent["features"]["byo_key_required"]),
        },
        "tokens": tokens,
        "tokens_monthly_remaining": tokens_monthly_remaining,  # CHANGED:
        "tokens_remaining_total": tokens_remaining_total,  # CHANGED:

        # UI links (optional)
        "links": links,  # CHANGED:
        "plugin_update": plugin_update_snapshot(),  # CHANGED:

        "entitlements_source": ent.get("source"),
    }


# ------------------------------

# ------------------------------
# Stripe Billing Portal (one-time session URLs)
# ------------------------------
# CHANGED:
# - WP must open a one-time Stripe Billing Portal session URL inside the popup.
# - We ONLY mint these URLs on demand during /license/verify/?intent=billing_portal&portal_session=1.
# - We NEVER cache these session URLs (HTTP no-store + no server-side persistence).

_STRIPE_CUSTOMER_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days (safe to cache customer id only)  # CHANGED:


def _resolve_stripe_secret_key() -> str:  # CHANGED:
    """
    Resolve the Stripe secret key in a bulletproof way.

    Spec (LOCKED):
    - If PPA_STRIPE_MODE=live -> use STRIPE_LIVE_SECRET_KEY
    - Else (test) -> use STRIPE_TEST_SECRET_KEY
    - Fallback to STRIPE_SECRET_KEY / STRIPE_API_KEY / PPA_STRIPE_SECRET_KEY if present

    Safety:
    - Never prints secrets
    """
    mode = (_opt_str(os.environ.get("PPA_STRIPE_MODE")) or "").lower()

    candidates = []
    if mode == "live":
        candidates.append(_opt_str(os.environ.get("STRIPE_LIVE_SECRET_KEY")))
    else:
        candidates.append(_opt_str(os.environ.get("STRIPE_TEST_SECRET_KEY")))

    # Fallbacks (legacy names or alternate deployments).
    candidates.extend(
        [
            _opt_str(os.environ.get("STRIPE_SECRET_KEY")),
            _opt_str(os.environ.get("STRIPE_API_KEY")),
            _opt_str(os.environ.get("PPA_STRIPE_SECRET_KEY")),
            _opt_str(os.environ.get("STRIPE_LIVE_SECRET_KEY")),
            _opt_str(os.environ.get("STRIPE_TEST_SECRET_KEY")),
        ]
    )

    for c in candidates:
        if c:
            return c

    raise APIError(
        code="stripe_misconfig",
        message="Stripe is not configured.",
        http_status=503,
        err_type="server_error",
    )


def _looks_like_stripe_customer_id(value: Optional[str]) -> bool:  # CHANGED:
    s = _opt_str(value) or ""
    return s.startswith("cus_") and len(s) >= 8


def _stripe_customer_cache_key(license_key: str) -> str:  # CHANGED:
    # Cache is safe here: it stores ONLY the customer id, never a session URL.
    return f"ppa:stripe_customer:{license_key}"


def _find_stripe_customer_id_in_models(lic: License, license_key: str) -> Optional[str]:  # CHANGED:
    """
    Best-effort DB lookup for an existing Stripe customer id.

    We do NOT assume a specific schema, because your License model does not include Stripe fields.
    We introspect installed models to find a plausible stripe_customer_id tied to this license.

    Returns cus_... or None.
    """
    try:
        for model in apps.get_models():
            # Skip unmanaged/proxy models safely.
            try:
                fields = [f for f in model._meta.get_fields() if hasattr(f, "name")]
                field_names = {f.name for f in fields}
            except Exception:
                continue

            if "stripe_customer_id" not in field_names:
                continue

            # Prefer FK to License if present.
            license_fk_field = None
            try:
                for f in fields:
                    if getattr(f, "is_relation", False) and getattr(f, "related_model", None) is License:
                        if bool(getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False)):
                            license_fk_field = f.name
                            break
            except Exception:
                license_fk_field = None

            license_key_field = "license_key" if "license_key" in field_names else None

            qs = model.objects.all()
            if license_fk_field:
                qs = qs.filter(**{license_fk_field: lic})
            elif license_key_field:
                qs = qs.filter(**{license_key_field: license_key})
            else:
                continue

            try:
                obj = qs.exclude(stripe_customer_id__isnull=True).exclude(stripe_customer_id="").first()
            except Exception:
                continue

            if not obj:
                continue

            val = _opt_str(getattr(obj, "stripe_customer_id", None))
            if _looks_like_stripe_customer_id(val):
                return val
    except Exception:
        return None

    return None


def _get_or_create_stripe_customer_id(*, lic: License, license_key: str, site_url: str) -> str:  # CHANGED:
    """
    Return a Stripe customer id (cus_...).

    Strategy (bulletproof):
    1) Cache lookup
    2) DB introspection lookup
    3) Stripe search (metadata)
    4) Create a new Stripe customer with metadata (no email required)

    NOTE:
    - We cache ONLY the customer id (safe).
    - We do NOT store the one-time portal session URL anywhere.
    """
    cache_key = _stripe_customer_cache_key(license_key)
    try:
        cached = _opt_str(cache.get(cache_key))
        if _looks_like_stripe_customer_id(cached):
            return cached
    except Exception:
        pass

    existing = _find_stripe_customer_id_in_models(lic, license_key)
    if _looks_like_stripe_customer_id(existing):
        try:
            cache.set(cache_key, existing, timeout=_STRIPE_CUSTOMER_CACHE_TTL_SECONDS)
        except Exception:
            pass
        return existing

    # Stripe-side lookup (best effort): try to find an existing customer by metadata.
    # This avoids creating a fresh customer that wouldn't show the real subscription in the Portal.  # CHANGED:
    try:
        import stripe  # local import keeps licensing boot resilient

        stripe.api_key = _resolve_stripe_secret_key()

        # 1) Try Subscription search by common metadata keys.  # CHANGED:
        for meta_key in ("ppa_license_key", "license_key", "ppa_license", "ppa_key"):
            try:
                res = stripe.Subscription.search(
                    query=f"metadata['{meta_key}']:'{license_key}'",
                    limit=1,
                )
                data = getattr(res, "data", None) or []
                if data:
                    sub = data[0]
                    cust = sub.get("customer") if isinstance(sub, dict) else getattr(sub, "customer", None)
                    cust = _opt_str(cust)
                    if _looks_like_stripe_customer_id(cust):
                        try:
                            cache.set(cache_key, cust, timeout=_STRIPE_CUSTOMER_CACHE_TTL_SECONDS)
                        except Exception:
                            pass
                        return cust
            except Exception:
                continue

        # 2) Try Customer search by metadata keys.  # CHANGED:
        for meta_key in ("ppa_license_key", "license_key", "ppa_license", "ppa_key"):
            try:
                res = stripe.Customer.search(
                    query=f"metadata['{meta_key}']:'{license_key}'",
                    limit=1,
                )
                data = getattr(res, "data", None) or []
                if data:
                    cust_obj = data[0]
                    cust_id = cust_obj.get("id") if isinstance(cust_obj, dict) else getattr(cust_obj, "id", None)
                    cust_id = _opt_str(cust_id)
                    if _looks_like_stripe_customer_id(cust_id):
                        try:
                            cache.set(cache_key, cust_id, timeout=_STRIPE_CUSTOMER_CACHE_TTL_SECONDS)
                        except Exception:
                            pass
                        return cust_id
            except Exception:
                continue

    except Exception:
        # Fail safe: if Stripe search isn't available in this account/version, fall through to create.  # CHANGED:
        pass

    # Create customer (best effort).
    try:
        import stripe  # local import keeps licensing boot resilient

        stripe.api_key = _resolve_stripe_secret_key()

        created = stripe.Customer.create(
            description="PostPress AI",
            metadata={
                "ppa_license_key": license_key,
                "ppa_site_url": site_url,
            },
        )
        cust_id = _opt_str(getattr(created, "id", None))
        if not _looks_like_stripe_customer_id(cust_id):
            raise APIError(
                code="stripe_customer_invalid",
                message="Unable to create Stripe customer.",
                http_status=503,
                err_type="server_error",
            )

        try:
            cache.set(cache_key, cust_id, timeout=_STRIPE_CUSTOMER_CACHE_TTL_SECONDS)
        except Exception:
            pass
        return cust_id

    except APIError:
        raise
    except Exception:
        raise APIError(
            code="stripe_customer_error",
            message="Billing Portal temporarily unavailable.",
            http_status=503,
            err_type="server_error",
        )


def _mint_billing_portal_session_url(*, lic: License, license_key: str, site_url: str, return_url: str) -> str:  # CHANGED:
    """
    Mint a one-time Stripe Billing Portal session URL.

    Requirements (LOCKED):
    - Returns only https://billing.stripe.com/p/session/... URLs
    - Must NOT fall back to /p/login
    - Must NOT be cached
    """
    try:
        import stripe  # local import keeps licensing boot resilient

        stripe.api_key = _resolve_stripe_secret_key()

        customer_id = _get_or_create_stripe_customer_id(lic=lic, license_key=license_key, site_url=site_url)

        # Sanity: return_url must be a safe absolute URL. Prefer the validated site_url.  # CHANGED:
        safe_return = _safe_account_url(return_url) or _safe_account_url(site_url) or site_url

        sess = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=safe_return,
        )
        url = _opt_str(getattr(sess, "url", None))
        url = _safe_stripe_billing_portal_session_url(url)
        if not url:
            raise APIError(
                code="missing_or_invalid_session_url",
                message="Billing Portal temporarily unavailable.",
                http_status=503,
                err_type="server_error",
            )
        return url

    except APIError:
        raise
    except Exception:
        raise APIError(
            code="stripe_portal_error",
            message="Billing Portal temporarily unavailable.",
            http_status=503,
            err_type="server_error",
        )


def _wants_billing_portal_session(request: HttpRequest, payload: Dict[str, Any]) -> bool:  # CHANGED:
    """Determine whether the caller is requesting a one-time billing portal session."""
    try:
        intent = _opt_str(request.GET.get("intent")) or ""
        intent = intent.strip().lower()
    except Exception:
        intent = ""

    # Accept common truthy values.
    try:
        portal_session = _opt_str(request.GET.get("portal_session"))
    except Exception:
        portal_session = None

    if portal_session is None:
        # Back-compat: allow payload to request it too (some clients send it in JSON).
        portal_session = _opt_str(payload.get("portal_session"))

    portal_flag = (portal_session or "").strip().lower() in ("1", "true", "yes", "on")

    return (intent == "billing_portal") or portal_flag


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

    CHANGED:
      On error states (inactive/limit), include deterministic contract snapshot in `data`
      when possible so WP admin can still render Plan/Sites/Tokens.
    """
    base_data: Optional[Dict[str, Any]] = None  # CHANGED:
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="activate", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)

        # Build deterministic payload early so errors can still return usable UI data.  # CHANGED:
        base_data = {
            "license": _license_contract_snapshot(license_key, lic),
            "activation": {"site_url": site_url, "activated": False},
        }

        _ensure_license_active(lic)

        act = Activation.objects.filter(license=lic, site_url=site_url).first()
        if act:
            _touch_activation(act, force=True)  # explicit action -> write
            base_data["license"] = _license_contract_snapshot(license_key, lic)  # CHANGED:
            base_data["activation"].update(
                {
                    "activated": True,
                    "activated_at": getattr(act, "activated_at", None),
                    "last_verified_at": getattr(act, "last_verified_at", None),
                    "already_active": True,
                }
            )
            return _json_ok(base_data)

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

        base_data["license"] = _license_contract_snapshot(license_key, lic)  # CHANGED: activation count changed
        base_data["activation"].update(
            {
                "activated": True,
                "activated_at": getattr(act, "activated_at", None),
                "last_verified_at": getattr(act, "last_verified_at", None),
                "already_active": False,
            }
        )
        return _json_ok(base_data)

    except APIError as e:
        return _json_err(e, data=base_data) if isinstance(base_data, dict) else _json_err(e)


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

    BILLING PORTAL (LOCKED REQUIREMENT):
      When called with:
        - ?intent=billing_portal&portal_session=1
      this endpoint MUST return a one-time Stripe Billing Portal session URL at:
        data.license.links.billing_portal = https://billing.stripe.com/p/session/...

      And MUST:
        - NOT return /p/login links
        - NOT cache the response (no-store)

    CHANGED:
      On error states (inactive/not_activated), we still include `data` with the deterministic
      plan/sites/tokens snapshot so WP can render Plan & Usage without guessing.
    """
    wants_portal_session = False  # CHANGED:
    base_data: Optional[Dict[str, Any]] = None  # CHANGED:
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        wants_portal_session = _wants_billing_portal_session(request, payload)  # CHANGED:

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="verify", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)

        # Build deterministic contract snapshot first (even if we error later).  # CHANGED:
        lic_snapshot = _license_contract_snapshot(license_key, lic)  # CHANGED:

        # If we're minting a one-time portal session URL, the response MUST NOT be cached.  # CHANGED:
        cache_ttl = 0 if wants_portal_session else VERIFY_CACHE_TTL_SECONDS  # CHANGED:

        base_data = {  # CHANGED:
            "cache_ttl_seconds": cache_ttl,
            "server_time": timezone.now(),
            "license": lic_snapshot,
            "activation": {
                "site_url": site_url,
                "activated": False,  # default; may be set True below
            },
        }

        # Activation lookup
        act = Activation.objects.filter(license=lic, site_url=site_url).first()
        if not act:
            # Site not activated: return error BUT keep deterministic data payload.  # CHANGED:
            raise APIError(
                code="not_activated",
                message="This site is not activated for this license.",
                http_status=403,
                err_type="activation",
            )

        # We found an activation row; expose it in the deterministic payload.  # CHANGED:
        base_data["activation"].update(
            {
                "activated": True,
                "activated_at": getattr(act, "activated_at", None),
                "last_verified_at": getattr(act, "last_verified_at", None),
            }
        )

        # Now enforce license active status (strict), but still allow deterministic payload on failure.  # CHANGED:
        _ensure_license_active(lic)

        _touch_activation(act, force=False)  # throttled writes for cacheability

        # CHANGED: Mint Billing Portal session URL only on demand.
        if wants_portal_session:
            session_url = _mint_billing_portal_session_url(
                lic=lic,
                license_key=license_key,
                site_url=site_url,
                return_url=site_url,
            )

            # Ensure links exists and override billing_portal with the one-time session URL.  # CHANGED:
            lic_links = base_data.get("license", {}).get("links")
            if not isinstance(lic_links, dict):
                base_data.setdefault("license", {})["links"] = {}
                lic_links = base_data["license"]["links"]

            lic_links["billing_portal"] = session_url  # CHANGED:

        resp = _json_ok(base_data)

        if wants_portal_session:
            # NEVER cache a one-time session URL.  # CHANGED:
            resp["Cache-Control"] = "private, no-store, max-age=0"
            resp["Pragma"] = "no-cache"
            resp["Expires"] = "0"
        else:
            resp["Cache-Control"] = f"private, max-age={VERIFY_CACHE_TTL_SECONDS}"

        return resp

    except APIError as e:
        # CHANGED: include deterministic data when possible (license/site parsed and license existed)
        try:
            if isinstance(base_data, dict):
                resp = _json_err(e, data=base_data)  # CHANGED:
            else:
                resp = _json_err(e)
        except Exception:
            resp = _json_err(e)

        # CHANGED: Never cache portal session responses (even errors) if the caller asked for a session.
        if wants_portal_session:
            resp["Cache-Control"] = "private, no-store, max-age=0"
            resp["Pragma"] = "no-cache"
            resp["Expires"] = "0"
        else:
            resp["Cache-Control"] = f"private, max-age={VERIFY_CACHE_TTL_SECONDS}"  # CHANGED:

        return resp


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

    CHANGED:
      On error states, include deterministic contract snapshot in `data` when possible.
    """
    base_data: Optional[Dict[str, Any]] = None  # CHANGED:
    try:
        payload = _parse_json_body(request)
        license_key = _clean_license_key(payload.get("license_key"))
        site_url = _normalize_site_url(payload.get("site_url"))

        _shared_key_header_valid(request)  # optional path

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="deactivate", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)

        # Build deterministic payload early so errors can still return usable UI data.  # CHANGED:
        base_data = {
            "license": _license_contract_snapshot(license_key, lic),
            "activation": {"site_url": site_url, "deactivated": False},
        }

        # Deactivate is cleanup-safe; we do NOT require active status.
        deleted, _ = Activation.objects.filter(license=lic, site_url=site_url).delete()

        base_data["license"] = _license_contract_snapshot(license_key, lic)  # CHANGED: activation count may change
        base_data["activation"].update(
            {
                "deactivated": True,
                "deleted": int(deleted),
            }
        )
        return _json_ok(base_data)

    except APIError as e:
        return _json_err(e, data=base_data) if isinstance(base_data, dict) else _json_err(e)


# ------------------------------
# Campaign issuance (protected)
# ------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # CHANGED:


def _clean_email(value: Any) -> str:  # CHANGED:
    if not isinstance(value, str):
        raise APIError(code="invalid_email", message="email must be a string.")
    email = value.strip().lower()
    if (not email) or (len(email) > 254) or (not _EMAIL_RE.match(email)):
        raise APIError(code="invalid_email", message="email format invalid.")
    return email


def _read_campaign_secret_env() -> str:  # CHANGED:
    return _opt_str(os.environ.get("PPA_CAMPAIGN_SECRET")) or ""


def _require_campaign_secret(request: HttpRequest) -> None:  # CHANGED:
    expected = _read_campaign_secret_env().strip()
    if not expected:
        raise APIError(
            code="server_misconfig",
            message="Campaign issuance not configured (PPA_CAMPAIGN_SECRET missing).",
            http_status=500,
            err_type="server_error",
        )

    provided = request.headers.get("X-PPA-CAMPAIGN-SECRET")
    if provided is None:
        provided = request.META.get("HTTP_X_PPA_CAMPAIGN_SECRET")
    provided = _norm(provided)

    if (not provided) or (not hmac.compare_digest(provided, expected)):
        raise APIError(
            code="unauthorized",
            message="Unauthorized.",
            http_status=401,
            err_type="auth_error",
        )


def _base32_no_pad(b: bytes) -> str:  # CHANGED:
    return base64.b32encode(b).decode("ascii").replace("=", "")


def _deterministic_license_key(*, email: str, campaign: str, secret: str) -> str:  # CHANGED:
    """Stable key per (email, campaign) using HMAC(secret, ...)."""
    msg = f"{campaign}|{email}".encode("utf-8")
    dig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    token = _base32_no_pad(dig)[:25].upper()
    parts = [token[i : i + 5] for i in range(0, 25, 5)]
    return "PPA-" + "-".join(parts)


def _get_or_create_customer_for_email(email: str):  # CHANGED:
    """Best-effort Customer create. Fails closed if model constraints prevent creation."""
    try:
        Customer = apps.get_model("postpress_ai", "Customer")
    except Exception:
        raise APIError(
            code="customer_model_missing",
            message="Customer model not available.",
            http_status=500,
            err_type="server_error",
        )

    existing = Customer.objects.filter(email__iexact=email).order_by("-id").first()
    if existing:
        return existing, False

    create_kwargs: Dict[str, Any] = {"email": email}

    try:
        fields = [f for f in Customer._meta.get_fields() if hasattr(f, "name")]
        field_names = {f.name for f in fields}
    except Exception:
        field_names = set()

    for cand in ("name", "full_name", "first_name", "last_name"):
        if cand in field_names:
            try:
                f = Customer._meta.get_field(cand)
                if (not getattr(f, "null", False)) and (not getattr(f, "blank", False)) and (f.default is models.NOT_PROVIDED):
                    create_kwargs[cand] = ""
            except Exception:
                continue

    try:
        obj = Customer.objects.create(**create_kwargs)
        return obj, True
    except Exception:
        raise APIError(
            code="customer_create_failed",
            message="Unable to create customer record.",
            http_status=500,
            err_type="server_error",
        )


@csrf_exempt
@require_POST
def campaign_issue(request: HttpRequest) -> JsonResponse:  # CHANGED:
    """Issue an expiring trial/campaign license key without Stripe automation.

    Auth:
      - X-PPA-CAMPAIGN-SECRET must match env PPA_CAMPAIGN_SECRET

    Input JSON:
      { "email": "...", "campaign": "trial_25k_14d", "source": "gravity_forms" }

    Output (license.v1 envelope):
      data: { license_key, expires_at, tokens_granted, idempotent, grant_created }
    """
    try:
        _require_campaign_secret(request)

        payload = _parse_json_body(request)
        email = _clean_email(payload.get("email"))
        campaign = _clean_plan_slug(payload.get("campaign"))
        source = _opt_str(payload.get("source")) or "gravity_forms"

        if campaign != TRIAL_CAMPAIGN_SLUG:
            raise APIError(code="invalid_campaign", message="Unsupported campaign.", http_status=400)

        secret = _read_campaign_secret_env().strip()
        if not secret:
            raise APIError(
                code="server_misconfig",
                message="Campaign issuance not configured (PPA_CAMPAIGN_SECRET missing).",
                http_status=500,
                err_type="server_error",
            )

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="campaign_issue", ip=ip, license_key=None)

        license_key = _deterministic_license_key(email=email, campaign=campaign, secret=secret)

        now = timezone.now()
        expires_at = now + timedelta(days=TRIAL_DURATION_DAYS)

        created_license = False
        grant_created = False

        with transaction.atomic():
            lic = License.objects.select_for_update().filter(key=license_key).first()

            if not lic:
                try:
                    lic = License.objects.create(
                        key=license_key,
                        plan_slug=campaign,
                        status="active",
                        max_sites=1,
                        unlimited_sites=False,
                        byo_key_required=False,
                        ai_included=True,
                        expires_at=expires_at,
                    )
                    created_license = True
                except IntegrityError:
                    lic = License.objects.select_for_update().filter(key=license_key).first()

            if not lic:
                raise APIError(code="issue_failed", message="Unable to issue license.", http_status=500, err_type="server_error")

            # Do NOT extend expiry on idempotent re-issues.
            if getattr(lic, "expires_at", None):
                expires_at = getattr(lic, "expires_at")

            customer, _ = _get_or_create_customer_for_email(email)

            # Grant tokens idempotently (prefers DB uniqueness when available).
            CreditLedger = None
            try:
                CreditLedger = apps.get_model("postpress_ai", "CreditLedger")
            except Exception:
                CreditLedger = None

            if not CreditLedger:
                raise APIError(code="grant_failed", message="Unable to grant campaign tokens.", http_status=500, err_type="server_error")

            try:
                field_names = {f.name for f in CreditLedger._meta.get_fields() if hasattr(f, "name")}
            except Exception:
                field_names = set()

            idem_hash = hashlib.sha256(f"{campaign}:{email}".encode("utf-8")).hexdigest()[:32]
            idem_key = f"camp:{campaign}:{idem_hash}"

            entry_type = "manual_adjust"  # already included in purchased_balance snapshot
            create_kwargs = {
                "customer": customer,
                "license": lic,
                "entry_type": entry_type,
                "amount": int(TRIAL_TOKENS_GRANTED),
                "description": f"Campaign grant: {campaign}",
                "meta": {"campaign": campaign, "email": email, "source": source},
            }

            try:
                if "idempotency_key" in field_names:
                    create_kwargs["idempotency_key"] = idem_key
                    try:
                        CreditLedger.objects.create(**create_kwargs)
                        grant_created = True
                    except IntegrityError:
                        grant_created = False
                else:
                    qs = CreditLedger.objects.filter(customer=customer, license=lic, entry_type=entry_type, amount=int(TRIAL_TOKENS_GRANTED))
                    try:
                        qs = qs.filter(meta__campaign=campaign, meta__email=email)  # type: ignore
                    except Exception:
                        qs = qs.filter(description=f"Campaign grant: {campaign}")
                    if qs.exists():
                        grant_created = False
                    else:
                        CreditLedger.objects.create(**create_kwargs)
                        grant_created = True
            except Exception:
                raise APIError(code="grant_failed", message="Unable to grant campaign tokens.", http_status=500, err_type="server_error")

        data = {
            "license_key": license_key,
            "expires_at": expires_at,
            "tokens_granted": int(TRIAL_TOKENS_GRANTED),
            "idempotent": (not created_license),
            "grant_created": bool(grant_created),
        }

        resp = _json_ok(data)
        resp["Cache-Control"] = "private, no-store, max-age=0"
        resp["Pragma"] = "no-cache"
        resp["Expires"] = "0"
        return resp

    except APIError as e:
        resp = _json_err(e)
        resp["Cache-Control"] = "private, no-store, max-age=0"
        resp["Pragma"] = "no-cache"
        resp["Expires"] = "0"
        return resp
