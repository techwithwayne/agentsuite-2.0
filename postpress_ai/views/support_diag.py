# /home/techwithwayne/agentsuite/postpress_ai/views/support_diag.py

"""PostPress AI — Support Diagnostics endpoint

Goal
----
Expose a *non-secret*, paste-ready snapshot of server/runtime configuration for
support tickets.

Security rules (DO NOT VIOLATE)
------------------------------
- No secrets: no API keys, no DB creds, no cache endpoints/hosts.
- Only safe labels/types/modes/booleans.
- Stable in production; never hard-fail if optional pieces are missing.

Endpoint
--------
GET /postpress-ai/support/diag/

Response
--------
{
  "ok": true,
  "ver": "support.diag.v1",
  "data": {
    "git_sha": "baa13cf",
    "env": "render",
    "server_time": "2026-02-28T...Z",
    "cache_backend": "django.core.cache.backends.filebased.FileBasedCache",
    "db_engine": "django.db.backends.postgresql",
    "stripe": {"mode": "live", "has_live_secret": true, ...},
    "features": {"byo_supported": true, "included_supported": true}
  },
  "paste": "...\n"
}
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import caches
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone


DIAG_VER = "support.diag.v1"


def _detect_env() -> str:
    v = (os.environ.get("PPA_ENV") or os.environ.get("DJANGO_ENV") or "").strip().lower()
    if v:
        return v
    if os.environ.get("RENDER"):
        return "render"
    if os.environ.get("HEROKU_APP_NAME"):
        return "heroku"
    return "local"


def _detect_git_sha() -> str:
    candidates = [
        "PPA_BUILD_SHA",
        "GIT_SHA",
        "COMMIT_SHA",
        "RENDER_GIT_COMMIT",
        "SOURCE_VERSION",
        "VCS_REF",
        "HEROKU_SLUG_COMMIT",
    ]
    for k in candidates:
        raw = (os.environ.get(k) or "").strip().strip('"').strip("'")
        if raw:
            return raw[:12]

    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        sha = out.decode("utf-8", errors="ignore").strip()
        return sha[:12]
    except Exception:
        return ""


def _cache_backend_label() -> str:
    # Prefer settings (safe) so we never touch backend connection details.
    try:
        cfg = getattr(settings, "CACHES", {}) or {}
        backend = ((cfg.get("default") or {}).get("BACKEND") or "").strip()
        if backend:
            return backend
    except Exception:
        pass

    # Fallback to instantiated cache class label.
    try:
        c = caches["default"]
        return f"{c.__class__.__module__}.{c.__class__.__name__}"
    except Exception:
        return ""


def _db_engine_label() -> str:
    try:
        db = getattr(settings, "DATABASES", {}) or {}
        return str(((db.get("default") or {}).get("ENGINE") or "")).strip()
    except Exception:
        return ""


def _stripe_mode() -> Dict[str, Any]:
    # Only report presence/prefix — never leak keys.
    live_secret = (os.environ.get("STRIPE_LIVE_SECRET_KEY") or "").strip()
    generic_secret = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    test_secret = (os.environ.get("STRIPE_TEST_SECRET_KEY") or "").strip()

    mode = "unknown"
    if live_secret or generic_secret.startswith("sk_live_"):
        mode = "live"
    elif test_secret or generic_secret.startswith("sk_test_"):
        mode = "test"

    return {
        "mode": mode,
        "has_live_secret": bool(live_secret),
        "has_test_secret": bool(test_secret),
        "has_generic_secret": bool(generic_secret),
    }


def _feature_flags() -> Dict[str, Optional[bool]]:
    """Best-effort: does this server support BYO and Included modes at all?"""

    byo: Optional[bool] = None
    included: Optional[bool] = None

    # Fast path: PLAN_DEFAULTS exists in your license view module in many builds.
    try:
        from postpress_ai.views.license import PLAN_DEFAULTS  # type: ignore

        # (max_sites, unlimited_sites, monthly_tokens, ai_included, byo_required)
        vals = list(getattr(PLAN_DEFAULTS, "values")())
        if vals:
            try:
                included = bool(any(bool(v[3]) for v in vals))
                byo = bool(any(bool(v[4]) for v in vals))
            except Exception:
                pass
    except Exception:
        pass

    # DB path: Plan model (if present). Keep it soft-fail.
    try:
        from postpress_ai.models.plan import Plan  # type: ignore

        if hasattr(Plan, "ai_mode"):
            byo_val = getattr(Plan, "AI_BYO_KEY", "byo_key")
            inc_val = getattr(Plan, "AI_INCLUDED", "included")
            qs = Plan.objects
            if hasattr(Plan, "is_active"):
                qs = qs.filter(is_active=True)
            if byo is None:
                byo = qs.filter(ai_mode=byo_val).exists()
            if included is None:
                included = qs.filter(ai_mode=inc_val).exists()
    except Exception:
        pass

    return {"byo_supported": byo, "included_supported": included}


def support_diag(request: HttpRequest, *args: Any, **kwargs: Any):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    data = {
        "git_sha": _detect_git_sha(),
        "env": _detect_env(),
        "server_time": timezone.now().isoformat(),
        "cache_backend": _cache_backend_label(),
        "db_engine": _db_engine_label(),
        "stripe": _stripe_mode(),
        "features": _feature_flags(),
    }

    paste = (
        "PostPress AI — Support Diag\n"
        f"env: {data.get('env') or '-'}\n"
        f"git_sha: {data.get('git_sha') or '-'}\n"
        f"server_time: {data.get('server_time') or '-'}\n"
        f"cache_backend: {data.get('cache_backend') or '-'}\n"
        f"db_engine: {data.get('db_engine') or '-'}\n"
        f"stripe.mode: {(data.get('stripe') or {}).get('mode') or '-'}\n"
        f"features.byo_supported: {(data.get('features') or {}).get('byo_supported')}\n"
        f"features.included_supported: {(data.get('features') or {}).get('included_supported')}\n"
    )

    resp = JsonResponse({"ok": True, "ver": DIAG_VER, "data": data, "paste": paste}, status=200)

    # Make caching explicit for support diagnostics.
    resp["Cache-Control"] = "no-store"
    resp["X-PPA-View"] = "support-diag"

    return resp
