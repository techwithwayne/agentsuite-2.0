"""
Shared utilities for PostPress AI views.
Extracted to avoid circular imports.
"""

from __future__ import annotations

# ========= CHANGE LOG =========
# 2026-01-04: OPTION A: _ppa_key_ok now supports license_key + site_url auth for protected endpoints
#            (customers should NOT set shared key per site). Shared key remains optional/internal.
#            No endpoint/payload/CORS changes.
# 2026-01-04: FIX (ONE-SHOT): Make Option A auth bulletproof for WP proxy calls:
#            - Accept X-PPA-Key as the license key (customer domains).
#            - Accept X-PPA-Install as site_url (WP proxy will send it).
#            - Activation match is tolerant (scheme/www/path/trailing slash differences).
#            - License lookup is tolerant (tries model helpers + common field names + sha digests).
#            - Adds short cache to avoid repeated DB work.                                            # CHANGED:

import hashlib  # CHANGED:
import json
import logging
import os
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

# Constants
VERSION = "postpress-ai.v2.1-2025-08-14"
log = logging.getLogger("webdoctor")


def _normalize_header_value(v: Optional[str]) -> str:
    """Trim common wrapper quotes and CR/LF. Do NOT log actual values."""
    if not v:
        return ""
    return v.strip().strip("'").strip('"').replace("\r", "").replace("\n", "")


def _is_test_env(request: HttpRequest) -> bool:
    """Detect Django test client / pytest context."""
    if any(
        [
            any("test" in (arg or "").lower() for arg in sys.argv),
            "PYTEST_CURRENT_TEST" in os.environ,
            os.environ.get("DJANGO_TESTING") == "1",
            os.environ.get("UNITTEST_RUNNING") == "1",
        ]
    ):
        return True
    host = (request.META.get("HTTP_HOST") or "").lower()
    srv = (request.META.get("SERVER_NAME") or "").lower()
    return host == "testserver" or srv == "testserver"


def _read_shared_key_env_or_settings() -> str:
    """
    Shared key source (internal/proxy path).

    Preferred: os.environ["PPA_SHARED_KEY"] (consistent with licensing endpoints).
    Fallback: settings.PPA_SHARED_KEY (backwards compatibility for older deployments).

    NEVER log the secret itself; lengths only.
    """
    env_val = _normalize_header_value(os.environ.get("PPA_SHARED_KEY", ""))  # CHANGED:
    if env_val:
        return env_val  # CHANGED:
    return _normalize_header_value(getattr(settings, "PPA_SHARED_KEY", ""))  # CHANGED:


def _normalize_site_url_strict(raw: str) -> str:
    """
    Strict-ish normalizer:
    - require http(s)
    - lower-case host
    - drop path/query/fragment
    - drop trailing slash
    - keep port if present
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        # Prefer the model normalizer if present (keeps canonical behavior).
        from postpress_ai.models.activation import Activation  # local import avoids cycles  # CHANGED:

        model_norm = getattr(Activation, "normalize_site_url", None)
        if callable(model_norm):
            out = model_norm(raw)
            return (out or "").strip().rstrip("/")
    except Exception:
        pass

    try:
        u = urlparse(raw)
        if u.scheme not in ("http", "https"):
            return ""
        if not u.hostname:
            return ""
        host = u.hostname.lower()
        port = f":{u.port}" if u.port else ""
        return f"{u.scheme}://{host}{port}".rstrip("/")
    except Exception:
        return ""


def _normalize_site_url_loose(raw: str) -> str:
    """
    Loose normalizer used ONLY for comparisons:
    - strips scheme
    - strips leading www.
    - keeps host (and port if present)
    - ignores path/query/fragment
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        if raw.startswith("//"):
            raw = "https:" + raw
        if not raw.lower().startswith(("http://", "https://")):
            raw = "https://" + raw
        u = urlparse(raw)
        host = (u.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return ""
        port = f":{u.port}" if u.port else ""
        return f"{host}{port}"
    except Exception:
        return ""


def _site_variants(raw_site: str) -> Dict[str, str]:
    """
    Build a small set of site variants so Activation match works even if stored differently.
    """
    strict = _normalize_site_url_strict(raw_site)
    loose = _normalize_site_url_loose(raw_site)
    out = {"strict": strict, "loose": loose}

    # Add scheme-flipped strict variants (some systems store http vs https).
    if strict.startswith("https://"):
        out["strict_http"] = "http://" + strict[len("https://") :]
    elif strict.startswith("http://"):
        out["strict_https"] = "https://" + strict[len("http://") :]

    # Add www variants for strict forms.
    if strict.startswith(("http://", "https://")):
        try:
            u = urlparse(strict)
            host = (u.hostname or "").lower()
            if host and not host.startswith("www."):
                port = f":{u.port}" if u.port else ""
                out["strict_www"] = f"{u.scheme}://www.{host}{port}".rstrip("/")
        except Exception:
            pass

    return {k: v for k, v in out.items() if v}


def _extract_license_key_and_site(request: HttpRequest) -> Dict[str, str]:
    """
    Pull license_key + site_url from either JSON body or headers.

    Body keys:
      - license_key
      - site_url

    Header keys:
      - X-PPA-License, X-PPA-License-Key
      - X-PPA-Site, X-PPA-Site-Url
      - X-PPA-Install              (WP proxy site identity)                            # CHANGED:
      - X-PPA-Key                  (customer license key in WP proxy)                  # CHANGED:
      - Authorization: Bearer <key>  OR  License <key>
    """
    payload = _parse_json_body(request)
    lic = (payload.get("license_key") or "").strip()
    site = (payload.get("site_url") or "").strip()

    if not lic:
        lic = _normalize_header_value(request.META.get("HTTP_X_PPA_LICENSE", ""))
    if not lic:
        lic = _normalize_header_value(request.META.get("HTTP_X_PPA_LICENSE_KEY", ""))

    if not site:
        site = _normalize_header_value(request.META.get("HTTP_X_PPA_SITE", ""))
    if not site:
        site = _normalize_header_value(request.META.get("HTTP_X_PPA_SITE_URL", ""))

    # CHANGED: WP proxy header that should identify the customer install.
    if not site:
        site = _normalize_header_value(request.META.get("HTTP_X_PPA_INSTALL", ""))  # CHANGED:

    if not lic:
        auth = _normalize_header_value(request.META.get("HTTP_AUTHORIZATION", ""))
        if auth.lower().startswith("bearer "):
            lic = auth.split(" ", 1)[1].strip()
        elif auth.lower().startswith("license "):
            lic = auth.split(" ", 1)[1].strip()

    # CHANGED: Treat X-PPA-Key as license key fallback for customer calls.
    # This is safe because we only consult Option A when shared-key auth fails.
    if not lic:
        lic = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))  # CHANGED:

    if len(lic) > 200:
        lic = lic[:200]
    if len(site) > 400:
        site = site[:400]

    return {"license_key": lic, "site_url": site}


def _find_license_record(license_key: str):
    """
    Tolerant license lookup:
    - tries common classmethods (lookup/from_key/etc.)
    - tries common field names (key/license_key)
    - tries common digest fields (sha256/sha1) if present
    """
    license_key = (license_key or "").strip()
    if not license_key:
        return None

    from postpress_ai.models.license import License  # local import  # CHANGED:

    # 1) Try helper methods if the model provides them.
    for mname in ("lookup", "from_key", "by_key", "get_by_key", "resolve"):
        fn = getattr(License, mname, None)
        if callable(fn):
            try:
                lic = fn(license_key)
                if lic:
                    return lic
            except Exception:
                pass

    # 2) Try common plaintext fields.
    try:
        field_names = {f.name for f in License._meta.fields}  # type: ignore[attr-defined]
    except Exception:
        field_names = set()

    for fname in ("key", "license_key", "raw_key", "plaintext_key"):
        if fname in field_names:
            try:
                lic = License.objects.filter(**{fname: license_key}).first()
                if lic:
                    return lic
            except Exception:
                pass

    # 3) Try common digest fields if they exist (best-effort).
    sha256_hex = hashlib.sha256(license_key.encode("utf-8")).hexdigest()
    sha1_hex = hashlib.sha1(license_key.encode("utf-8")).hexdigest()

    for fname, digest in (
        ("key_sha256", sha256_hex),
        ("sha256", sha256_hex),
        ("key_hash", sha256_hex),
        ("key_digest", sha256_hex),
        ("fingerprint", sha256_hex),
        ("key_sha1", sha1_hex),
        ("sha1", sha1_hex),
    ):
        if fname in field_names:
            try:
                lic = License.objects.filter(**{fname: digest}).first()
                if lic:
                    return lic
            except Exception:
                pass

    return None


def _activation_matches_site(license_obj, site_raw: str) -> bool:
    """
    Tolerant Activation match:
    - tries direct DB IN lookup against common site fields
    - falls back to scanning activations for that license and comparing loose normalized host
    """
    if not license_obj:
        return False

    from postpress_ai.models.activation import Activation  # local import  # CHANGED:

    variants = _site_variants(site_raw)
    strict_variants = {v for k, v in variants.items() if k.startswith("strict")}
    loose_target = variants.get("loose", "")

    # Figure out which field stores the site identity (default: site_url).
    try:
        field_names = {f.name for f in Activation._meta.fields}  # type: ignore[attr-defined]
    except Exception:
        field_names = set()

    site_field = "site_url" if "site_url" in field_names else ""
    if not site_field:
        for cand in ("install_url", "site", "url"):
            if cand in field_names:
                site_field = cand
                break

    # 1) Fast direct match on stored field if we found it.
    if site_field and strict_variants:
        try:
            qs = Activation.objects.filter(license=license_obj).filter(**{f"{site_field}__in": list(strict_variants)})
            if qs.first():
                return True
        except Exception:
            pass

    # 2) Scan & compare loose host form (handles any stored formatting).
    if not loose_target:
        loose_target = _normalize_site_url_loose(site_raw)

    if not loose_target:
        return False

    try:
        qs = Activation.objects.filter(license=license_obj)
        # Only pull the one column we need to compare.
        if site_field:
            vals = qs.values_list(site_field, flat=True)[:200]
        else:
            # Worst case fallback: pull full objects (still bounded).
            vals = [getattr(a, "site_url", "") for a in qs[:200]]
        for v in vals:
            if _normalize_site_url_loose(str(v or "")) == loose_target:
                return True
    except Exception:
        return False

    return False


def _license_activation_ok(request: HttpRequest) -> bool:
    """
    Customer auth:
    Return True if:
      - license key exists
      - license is active
      - activation exists for the provided site (tolerant match)
    """
    try:
        data = _extract_license_key_and_site(request)
        license_key = (data.get("license_key") or "").strip()
        site_url_raw = (data.get("site_url") or "").strip()

        if not license_key or not site_url_raw:
            return False

        # Cache result briefly to reduce DB work.
        try:
            from django.core.cache import cache  # CHANGED:

            cache_key = "ppa_auth:" + hashlib.sha256(
                (license_key + "|" + _normalize_site_url_loose(site_url_raw)).encode("utf-8")
            ).hexdigest()
            cached = cache.get(cache_key)
            if cached is True:
                return True
            if cached is False:
                return False
        except Exception:
            cache = None  # type: ignore

        lic = _find_license_record(license_key)  # CHANGED:
        if not lic:
            if cache:
                cache.set(cache_key, False, 60)
            return False

        # Active check (method preferred).
        is_active = getattr(lic, "is_active", None)
        if callable(is_active):
            if not is_active():
                if cache:
                    cache.set(cache_key, False, 60)
                return False
        else:
            status = str(getattr(lic, "status", "") or "").strip().lower()
            if status != "active":
                if cache:
                    cache.set(cache_key, False, 60)
                return False

        if not _activation_matches_site(lic, site_url_raw):  # CHANGED:
            if cache:
                cache.set(cache_key, False, 60)
            return False

        if cache:
            cache.set(cache_key, True, 120)
        return True

    except Exception:
        return False


def _ppa_key_ok(request: HttpRequest) -> bool:
    """
    Validate request authorization for protected endpoints.

    INTERNAL / PROXY PATH:
      - X-PPA-Key must match server shared key

    CUSTOMER PATH (Option A):
      - If shared-key check fails, allow access if license_key + site_url verify
        against License + Activation (active + activated).
    """
    provided = _normalize_header_value(request.META.get("HTTP_X_PPA_KEY", ""))
    expected = _read_shared_key_env_or_settings()

    if _is_test_env(request):
        log.info(
            "[PPA][auth] test-bypass=True expected_len=%s provided_len=%s",
            len(expected),
            len(provided),
        )
        return True

    shared_ok = bool(expected) and (provided == expected)

    lic_ok = False
    if not shared_ok:
        lic_ok = _license_activation_ok(request)

    ok = bool(shared_ok or lic_ok)

    log.info(
        "[PPA][auth] expected_len=%s provided_len=%s shared_match=%s license_fallback=%s ok=%s origin=%s",
        len(expected),
        len(provided),
        bool(shared_ok),
        bool(lic_ok),
        bool(ok),
        _normalize_header_value(request.META.get("HTTP_ORIGIN")),
    )
    return ok


def _allowed_origin(origin: Optional[str]) -> Optional[str]:
    """Reflect CORS only for explicitly allowed origins."""
    if not origin:
        return None
    origin = origin.strip()
    allowed = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    allowed.update(getattr(settings, "PPA_ALLOWED_ORIGINS", []))
    return origin if origin in allowed else None


def _with_cors(resp: HttpResponse, request: HttpRequest) -> HttpResponse:
    """Apply CORS headers when the Origin is explicitly allowed."""
    origin = _allowed_origin(request.META.get("HTTP_ORIGIN"))
    if origin:
        resp["Access-Control-Allow-Origin"] = origin
        resp["Vary"] = "Origin"
        resp["Access-Control-Allow-Headers"] = "Content-Type, X-PPA-Key, X-PPA-Install, X-PPA-Version"
        resp["Access-Control-Allow-Methods"] = "POST, OPTIONS, GET"
        resp["Access-Control-Allow-Credentials"] = "true"
    return resp


def _json_response(payload: Dict[str, Any], status: int = 200, request: Optional[HttpRequest] = None) -> JsonResponse:
    """Attach `ver` automatically and reflect CORS if we have a request context."""
    if "ver" not in payload:
        payload["ver"] = VERSION
    resp = JsonResponse(payload, status=status)
    if request is not None:
        resp = _with_cors(resp, request)
    return resp


def _parse_json_body(request: HttpRequest) -> Dict[str, Any]:
    """Best-effort JSON body parse. Returns {} on any error."""
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


def _is_url(val: Optional[str]) -> bool:
    """Light URL check used by the store normalizer."""
    try:
        if not val:
            return False
        u = urlparse(val)
        return bool(u.scheme) and bool(u.netloc)
    except Exception:
        return False
