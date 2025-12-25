# /home/techwithwayne/agentsuite/postpress_ai/views/license.py
"""
postpress_ai.views.license

Licensing endpoints (Django is authoritative):
- /license/activate/
- /license/verify/
- /license/deactivate/

LOCKED RULES
- WordPress never decides license validity.
- WP → admin-ajax → PHP controller → Django only.
- No browser → Django calls.
- No CORS / ALLOWED_HOSTS widening.
- Strict server-side (no grace period by default).

Response envelope (consistent):
  { "ok": true|false, "data": {...}, "error": {...}, "ver": "license.v1" }

"""

from __future__ import annotations  # CHANGED:

# ========= CHANGE LOG =========  # CHANGED:
# 2025-12-24: Initial implementation of licensing endpoints with strict validation, shared-key auth,  # CHANGED:
#            URL normalization, activation limits, and cache-based rate limiting.                   # CHANGED:
# 2025-12-24: Auth source corrected: shared key is read from os.environ["PPA_SHARED_KEY"] only.     # CHANGED:
#            (Matches hardened proxy behavior: tests must patch os.environ, not settings.)         # CHANGED:
# 2025-12-24: Deactivate is allowed even if license is inactive/expired (cleanup-safe + idempotent).# CHANGED:
# 2025-12-24: Harden auth compare: normalize header/env values + constant-time compare (prevents false 401s).  # CHANGED:
# 2025-12-24: FIX: Enforce LOCKED env auth semantic: read via os.environ["PPA_SHARED_KEY"] (not .get()).       # CHANGED:

import json  # CHANGED:
import os  # CHANGED:
import re  # CHANGED:
import hmac  # CHANGED:
from dataclasses import dataclass  # CHANGED:
from typing import Any, Dict, Optional  # CHANGED:
from urllib.parse import urlparse  # CHANGED:

from django.core.cache import cache  # CHANGED:
from django.http import HttpRequest, JsonResponse  # CHANGED:
from django.utils import timezone  # CHANGED:
from django.views.decorators.csrf import csrf_exempt  # CHANGED:
from django.views.decorators.http import require_POST  # CHANGED:

from postpress_ai.models.activation import Activation  # CHANGED:
from postpress_ai.models.license import License  # CHANGED:

API_VER = "license.v1"  # CHANGED:

# ------------------------------  # CHANGED:
# Rate limit (cache-based)        # CHANGED:
# ------------------------------  # CHANGED:
# Note: This is intentionally simple + deterministic. For production upgrades, you can later move  # CHANGED:
# this into a dedicated throttling module (still server-side) without changing the endpoint shape. # CHANGED:

RL_WINDOW_SECONDS = 60  # CHANGED:
RL_IP_LIMIT_PER_WINDOW = 30  # CHANGED:  # per endpoint per IP per minute
RL_KEY_LIMIT_PER_WINDOW = 12  # CHANGED:  # per endpoint per license key per minute


@dataclass(frozen=True)  # CHANGED:
class APIError(Exception):  # CHANGED:
    """Internal exception for consistent JSON error responses."""  # CHANGED:

    code: str  # CHANGED:
    message: str  # CHANGED:
    http_status: int = 400  # CHANGED:
    err_type: str = "validation_error"  # CHANGED:


# ------------------------------  # CHANGED:
# Helpers                         # CHANGED:
# ------------------------------  # CHANGED:
def _json_ok(data: Dict[str, Any], status: int = 200) -> JsonResponse:  # CHANGED:
    return JsonResponse({"ok": True, "data": data, "ver": API_VER}, status=status)  # CHANGED:


def _json_err(e: APIError) -> JsonResponse:  # CHANGED:
    return JsonResponse(  # CHANGED:
        {  # CHANGED:
            "ok": False,  # CHANGED:
            "error": {  # CHANGED:
                "type": e.err_type,  # CHANGED:
                "code": e.code,  # CHANGED:
                "message": e.message,  # CHANGED:
            },  # CHANGED:
            "ver": API_VER,  # CHANGED:
        },  # CHANGED:
        status=e.http_status,  # CHANGED:
    )  # CHANGED:


def _get_client_ip(request: HttpRequest) -> str:  # CHANGED:
    """
    Conservative IP extraction.
    We DO NOT trust X-Forwarded-For here unless you explicitly want to later, behind a known proxy.
    """  # CHANGED:
    ip = request.META.get("REMOTE_ADDR") or ""  # CHANGED:
    return ip.strip()[:64] if ip else "unknown"  # CHANGED:


def _norm(value: Any) -> str:  # CHANGED:
    """
    Normalize auth values consistently:
    - cast to str
    - strip whitespace/newlines
    - rely on existing header normalizer patterns when possible
    """  # CHANGED:
    if value is None:  # CHANGED:
        return ""  # CHANGED:
    if not isinstance(value, str):  # CHANGED:
        try:  # CHANGED:
            value = str(value)  # CHANGED:
        except Exception:  # CHANGED:
            return ""  # CHANGED:
    return value.strip()  # CHANGED:


def _read_shared_key_env() -> str:  # CHANGED:
    """
    LOCKED AUTH SOURCE (env-only):

    Licensing must read from os.environ["PPA_SHARED_KEY"].
    We mirror that exact semantic, but safely handle missing env by returning "".

    NOTE:
      - Does NOT consult Django settings.
      - Does NOT log or return secrets.
    """  # CHANGED:
    try:  # CHANGED:
        return os.environ["PPA_SHARED_KEY"]  # CHANGED:
    except KeyError:  # CHANGED:
        return ""  # CHANGED:


def _get_shared_key() -> str:  # CHANGED:
    """
    Shared secret injected by the WP PHP controller server-side (X-PPA-Key).

    IMPORTANT (LOCKED / VERIFIED):
    Auth reads from os.environ["PPA_SHARED_KEY"], not Django settings.
    Tests must patch os.environ.
    """  # CHANGED:
    key = _read_shared_key_env()  # CHANGED:
    key = _norm(key)  # CHANGED:
    if not key:  # CHANGED:
        raise APIError(  # CHANGED:
            code="server_misconfig",  # CHANGED:
            message="Licensing not configured (PPA_SHARED_KEY missing).",  # CHANGED:
            http_status=500,  # CHANGED:
            err_type="server_error",  # CHANGED:
        )  # CHANGED:
    return key  # CHANGED:


def _require_shared_key(request: HttpRequest) -> None:  # CHANGED:
    """
    Require server-to-server auth header. This blocks any direct browser calls by default.
    """  # CHANGED:
    expected = _get_shared_key()  # CHANGED:

    # Prefer request.headers, fallback to META; normalize either way.  # CHANGED:
    provided = request.headers.get("X-PPA-Key")  # CHANGED:
    if provided is None:  # CHANGED:
        provided = request.META.get("HTTP_X_PPA_KEY")  # CHANGED:
    provided = _norm(provided)  # CHANGED:

    # Constant-time compare to avoid timing side-channels and reduce false mismatches.  # CHANGED:
    if (not provided) or (not hmac.compare_digest(provided, expected)):  # CHANGED:
        raise APIError(  # CHANGED:
            code="unauthorized",  # CHANGED:
            message="Unauthorized.",  # CHANGED:
            http_status=401,  # CHANGED:
            err_type="auth_error",  # CHANGED:
        )  # CHANGED:


def _rate_limit_or_raise(*, scope: str, ip: str, license_key: Optional[str]) -> None:  # CHANGED:
    """
    Cache-based fixed window limiter:
    - per endpoint per IP
    - per endpoint per license_key (if provided)

    Fail-closed on cache errors (conservative for a licensing system).
    """  # CHANGED:
    window = int(timezone.now().timestamp() // RL_WINDOW_SECONDS)  # CHANGED:
    ip_key = f"ppa:rl:{scope}:ip:{ip}:{window}"  # CHANGED:
    lk = (license_key or "").strip()  # CHANGED:
    lic_key = f"ppa:rl:{scope}:key:{lk}:{window}" if lk else None  # CHANGED:

    try:  # CHANGED:
        ip_count = cache.get(ip_key)  # CHANGED:
        if ip_count is None:  # CHANGED:
            cache.set(ip_key, 1, timeout=RL_WINDOW_SECONDS + 5)  # CHANGED:
            ip_count = 1  # CHANGED:
        else:  # CHANGED:
            ip_count = int(ip_count) + 1  # CHANGED:
            cache.set(ip_key, ip_count, timeout=RL_WINDOW_SECONDS + 5)  # CHANGED:

        if ip_count > RL_IP_LIMIT_PER_WINDOW:  # CHANGED:
            raise APIError(  # CHANGED:
                code="rate_limited",  # CHANGED:
                message="Too many requests. Try again shortly.",  # CHANGED:
                http_status=429,  # CHANGED:
                err_type="rate_limit",  # CHANGED:
            )  # CHANGED:

        if lic_key:  # CHANGED:
            k_count = cache.get(lic_key)  # CHANGED:
            if k_count is None:  # CHANGED:
                cache.set(lic_key, 1, timeout=RL_WINDOW_SECONDS + 5)  # CHANGED:
                k_count = 1  # CHANGED:
            else:  # CHANGED:
                k_count = int(k_count) + 1  # CHANGED:
                cache.set(lic_key, k_count, timeout=RL_WINDOW_SECONDS + 5)  # CHANGED:

            if k_count > RL_KEY_LIMIT_PER_WINDOW:  # CHANGED:
                raise APIError(  # CHANGED:
                    code="rate_limited",  # CHANGED:
                    message="Too many requests for this license key. Try again shortly.",  # CHANGED:
                    http_status=429,  # CHANGED:
                    err_type="rate_limit",  # CHANGED:
                )  # CHANGED:

    except APIError:  # CHANGED:
        raise  # CHANGED:
    except Exception:  # CHANGED:
        # Fail-closed: if cache misbehaves, we do not allow licensing operations to proceed.  # CHANGED:
        raise APIError(  # CHANGED:
            code="rate_limit_unavailable",  # CHANGED:
            message="Licensing temporarily unavailable.",  # CHANGED:
            http_status=503,  # CHANGED:
            err_type="server_error",  # CHANGED:
        )  # CHANGED:


def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:  # CHANGED:
    """
    Parse request body JSON safely. We never log secrets.
    """  # CHANGED:
    raw = request.body or b""  # CHANGED:
    if not raw:  # CHANGED:
        raise APIError(code="missing_body", message="Missing JSON body.")  # CHANGED:
    try:  # CHANGED:
        payload = json.loads(raw.decode("utf-8"))  # CHANGED:
    except Exception:  # CHANGED:
        raise APIError(code="invalid_json", message="Invalid JSON.")  # CHANGED:
    if not isinstance(payload, dict):  # CHANGED:
        raise APIError(code="invalid_json", message="JSON root must be an object.")  # CHANGED:
    return payload  # CHANGED:


_LICENSE_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{10,128}$")  # CHANGED:


def _clean_license_key(value: Any) -> str:  # CHANGED:
    if not isinstance(value, str):  # CHANGED:
        raise APIError(code="invalid_license_key", message="license_key must be a string.")  # CHANGED:
    key = value.strip()  # CHANGED:
    if not _LICENSE_KEY_RE.match(key):  # CHANGED:
        raise APIError(code="invalid_license_key", message="license_key format invalid.")  # CHANGED:
    return key  # CHANGED:


def _normalize_site_url(value: Any) -> str:  # CHANGED:
    """
    Normalization rules (strict, deterministic):
    - require http(s)
    - lower-case host
    - drop path/query/fragment
    - drop trailing slash
    - keep port if present
    - return scheme://host[:port]
    """  # CHANGED:
    if not isinstance(value, str):  # CHANGED:
        raise APIError(code="invalid_site_url", message="site_url must be a string.")  # CHANGED:
    raw = value.strip()  # CHANGED:
    if not raw:  # CHANGED:
        raise APIError(code="invalid_site_url", message="site_url is required.")  # CHANGED:

    # If your Activation model provides a canonical normalizer, prefer it.  # CHANGED:
    model_norm = getattr(Activation, "normalize_site_url", None)  # CHANGED:
    if callable(model_norm):  # CHANGED:
        normalized = model_norm(raw)  # CHANGED:
        if not isinstance(normalized, str) or not normalized.strip():  # CHANGED:
            raise APIError(code="invalid_site_url", message="site_url invalid.")  # CHANGED:
        return normalized.strip()  # CHANGED:

    parsed = urlparse(raw)  # CHANGED:
    if parsed.scheme not in ("http", "https"):  # CHANGED:
        raise APIError(code="invalid_site_url", message="site_url must include http:// or https://")  # CHANGED:
    if not parsed.hostname:  # CHANGED:
        raise APIError(code="invalid_site_url", message="site_url hostname missing.")  # CHANGED:

    host = parsed.hostname.lower()  # CHANGED:
    port = f":{parsed.port}" if parsed.port else ""  # CHANGED:
    return f"{parsed.scheme}://{host}{port}".rstrip("/")  # CHANGED:


def _get_license_or_raise(license_key: str) -> License:  # CHANGED:
    lic = License.objects.filter(key=license_key).first()  # CHANGED:
    if not lic:  # CHANGED:
        # Do not leak which keys exist.  # CHANGED:
        raise APIError(code="not_found", message="License not found.", http_status=404)  # CHANGED:
    return lic  # CHANGED:


def _ensure_license_active(lic: License) -> None:  # CHANGED:
    is_active = getattr(lic, "is_active", None)  # CHANGED:
    if callable(is_active):  # CHANGED:
        if not is_active():  # CHANGED:
            raise APIError(code="license_inactive", message="License is not active.", http_status=403)  # CHANGED:
        return  # CHANGED:

    # Fail-safe fallback if model method is missing.  # CHANGED:
    status = getattr(lic, "status", "")  # CHANGED:
    if str(status) != "active":  # CHANGED:
        raise APIError(code="license_inactive", message="License is not active.", http_status=403)  # CHANGED:


def _activation_count_for_license(lic: License) -> int:  # CHANGED:
    return Activation.objects.filter(license=lic).count()  # CHANGED:


def _license_limit_allows_site(lic: License) -> bool:  # CHANGED:
    if bool(getattr(lic, "unlimited_sites", False)):  # CHANGED:
        return True  # CHANGED:
    max_sites = int(getattr(lic, "max_sites", 0) or 0)  # CHANGED:
    if max_sites <= 0:  # CHANGED:
        return False  # CHANGED:
    return _activation_count_for_license(lic) < max_sites  # CHANGED:


def _mask_key(key: str) -> str:  # CHANGED:
    if not key:  # CHANGED:
        return ""  # CHANGED:
    if len(key) <= 8:  # CHANGED:
        return "*" * len(key)  # CHANGED:
    return f"{key[:4]}…{key[-4:]}"  # CHANGED:


def _touch_activation(act: Activation) -> None:  # CHANGED:
    act.last_verified_at = timezone.now()  # CHANGED:
    act.save(update_fields=["last_verified_at"])  # CHANGED:


# ------------------------------  # CHANGED:
# Endpoints                        # CHANGED:
# ------------------------------  # CHANGED:
@csrf_exempt  # CHANGED:
@require_POST  # CHANGED:
def license_activate(request: HttpRequest) -> JsonResponse:  # CHANGED:
    """
    Activate a site for a license key.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Output:
      ok + activation state (display-only; Django remains the source of truth)
    """  # CHANGED:
    try:  # CHANGED:
        _require_shared_key(request)  # CHANGED:
        payload = _parse_json_body(request)  # CHANGED:
        license_key = _clean_license_key(payload.get("license_key"))  # CHANGED:
        site_url = _normalize_site_url(payload.get("site_url"))  # CHANGED:

        ip = _get_client_ip(request)  # CHANGED:
        _rate_limit_or_raise(scope="activate", ip=ip, license_key=license_key)  # CHANGED:

        lic = _get_license_or_raise(license_key)  # CHANGED:
        _ensure_license_active(lic)  # CHANGED:

        act = Activation.objects.filter(license=lic, site_url=site_url).first()  # CHANGED:
        if act:  # CHANGED:
            _touch_activation(act)  # CHANGED:
            return _json_ok(  # CHANGED:
                {  # CHANGED:
                    "license": {  # CHANGED:
                        "key_masked": _mask_key(license_key),  # CHANGED:
                        "plan_slug": getattr(lic, "plan_slug", None),  # CHANGED:
                        "status": getattr(lic, "status", None),  # CHANGED:
                        "max_sites": getattr(lic, "max_sites", None),  # CHANGED:
                        "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),  # CHANGED:
                        "byo_key_required": bool(getattr(lic, "byo_key_required", False)),  # CHANGED:
                        "ai_included": bool(getattr(lic, "ai_included", False)),  # CHANGED:
                        "expires_at": getattr(lic, "expires_at", None),  # CHANGED:
                    },  # CHANGED:
                    "activation": {  # CHANGED:
                        "site_url": site_url,  # CHANGED:
                        "activated": True,  # CHANGED:
                        "activated_at": getattr(act, "activated_at", None),  # CHANGED:
                        "last_verified_at": getattr(act, "last_verified_at", None),  # CHANGED:
                        "already_active": True,  # CHANGED:
                    },  # CHANGED:
                }  # CHANGED:
            )  # CHANGED:

        if not _license_limit_allows_site(lic):  # CHANGED:
            raise APIError(  # CHANGED:
                code="site_limit_reached",  # CHANGED:
                message="Site activation limit reached for this plan.",  # CHANGED:
                http_status=403,  # CHANGED:
                err_type="plan_limit",  # CHANGED:
            )  # CHANGED:

        now = timezone.now()  # CHANGED:
        act = Activation.objects.create(  # CHANGED:
            license=lic,  # CHANGED:
            site_url=site_url,  # CHANGED:
            activated_at=now,  # CHANGED:
            last_verified_at=now,  # CHANGED:
        )  # CHANGED:

        return _json_ok(  # CHANGED:
            {  # CHANGED:
                "license": {  # CHANGED:
                    "key_masked": _mask_key(license_key),  # CHANGED:
                    "plan_slug": getattr(lic, "plan_slug", None),  # CHANGED:
                    "status": getattr(lic, "status", None),  # CHANGED:
                    "max_sites": getattr(lic, "max_sites", None),  # CHANGED:
                    "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),  # CHANGED:
                    "byo_key_required": bool(getattr(lic, "byo_key_required", False)),  # CHANGED:
                    "ai_included": bool(getattr(lic, "ai_included", False)),  # CHANGED:
                    "expires_at": getattr(lic, "expires_at", None),  # CHANGED:
                },  # CHANGED:
                "activation": {  # CHANGED:
                    "site_url": site_url,  # CHANGED:
                    "activated": True,  # CHANGED:
                    "activated_at": getattr(act, "activated_at", None),  # CHANGED:
                    "last_verified_at": getattr(act, "last_verified_at", None),  # CHANGED:
                    "already_active": False,  # CHANGED:
                },  # CHANGED:
            }  # CHANGED:
        )  # CHANGED:

    except APIError as e:  # CHANGED:
        return _json_err(e)  # CHANGED:


@csrf_exempt  # CHANGED:
@require_POST  # CHANGED:
def license_verify(request: HttpRequest) -> JsonResponse:  # CHANGED:
    """
    Verify a license + site activation.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Output:
      ok true if license active AND activation exists.
    """  # CHANGED:
    try:  # CHANGED:
        _require_shared_key(request)  # CHANGED:
        payload = _parse_json_body(request)  # CHANGED:
        license_key = _clean_license_key(payload.get("license_key"))  # CHANGED:
        site_url = _normalize_site_url(payload.get("site_url"))  # CHANGED:

        ip = _get_client_ip(request)  # CHANGED:
        _rate_limit_or_raise(scope="verify", ip=ip, license_key=license_key)  # CHANGED:

        lic = _get_license_or_raise(license_key)  # CHANGED:
        _ensure_license_active(lic)  # CHANGED:

        act = Activation.objects.filter(license=lic, site_url=site_url).first()  # CHANGED:
        if not act:  # CHANGED:
            raise APIError(  # CHANGED:
                code="not_activated",  # CHANGED:
                message="This site is not activated for this license.",  # CHANGED:
                http_status=403,  # CHANGED:
                err_type="activation",  # CHANGED:
            )  # CHANGED:

        _touch_activation(act)  # CHANGED:

        return _json_ok(  # CHANGED:
            {  # CHANGED:
                "license": {  # CHANGED:
                    "key_masked": _mask_key(license_key),  # CHANGED:
                    "plan_slug": getattr(lic, "plan_slug", None),  # CHANGED:
                    "status": getattr(lic, "status", None),  # CHANGED:
                    "max_sites": getattr(lic, "max_sites", None),  # CHANGED:
                    "unlimited_sites": bool(getattr(lic, "unlimited_sites", False)),  # CHANGED:
                    "byo_key_required": bool(getattr(lic, "byo_key_required", False)),  # CHANGED:
                    "ai_included": bool(getattr(lic, "ai_included", False)),  # CHANGED:
                    "expires_at": getattr(lic, "expires_at", None),  # CHANGED:
                },  # CHANGED:
                "activation": {  # CHANGED:
                    "site_url": site_url,  # CHANGED:
                    "activated": True,  # CHANGED:
                    "activated_at": getattr(act, "activated_at", None),  # CHANGED:
                    "last_verified_at": getattr(act, "last_verified_at", None),  # CHANGED:
                },  # CHANGED:
            }  # CHANGED:
        )  # CHANGED:

    except APIError as e:  # CHANGED:
        return _json_err(e)  # CHANGED:


@csrf_exempt  # CHANGED:
@require_POST  # CHANGED:
def license_deactivate(request: HttpRequest) -> JsonResponse:  # CHANGED:
    """
    Deactivate a site for a license.

    Input JSON:
      { "license_key": "...", "site_url": "https://example.com" }

    Output:
      ok true (idempotent)
    """  # CHANGED:
    try:  # CHANGED:
        _require_shared_key(request)  # CHANGED:
        payload = _parse_json_body(request)  # CHANGED:
        license_key = _clean_license_key(payload.get("license_key"))  # CHANGED:
        site_url = _normalize_site_url(payload.get("site_url"))  # CHANGED:

        ip = _get_client_ip(request)  # CHANGED:
        _rate_limit_or_raise(scope="deactivate", ip=ip, license_key=license_key)  # CHANGED:

        lic = _get_license_or_raise(license_key)  # CHANGED:
        # NOTE: Deactivate is cleanup-safe, so we intentionally do NOT require active status here.  # CHANGED:

        deleted, _ = Activation.objects.filter(license=lic, site_url=site_url).delete()  # CHANGED:

        return _json_ok(  # CHANGED:
            {  # CHANGED:
                "license": {  # CHANGED:
                    "key_masked": _mask_key(license_key),  # CHANGED:
                    "plan_slug": getattr(lic, "plan_slug", None),  # CHANGED:
                    "status": getattr(lic, "status", None),  # CHANGED:
                },  # CHANGED:
                "activation": {  # CHANGED:
                    "site_url": site_url,  # CHANGED:
                    "deactivated": True,  # CHANGED:
                    "deleted": int(deleted),  # CHANGED:
                },  # CHANGED:
            }  # CHANGED:
        )  # CHANGED:

    except APIError as e:  # CHANGED:
        return _json_err(e)  # CHANGED:
