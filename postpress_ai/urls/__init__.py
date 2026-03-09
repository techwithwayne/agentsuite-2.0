"""
PostPress AI  URL routes (package router)

CHANGE LOG
----------
2025-12-24
- FIX: Remove invalid import 'from .urls import ...' (no postpress_ai/urls/urls.py exists).
- KEEP: Provide deterministic urlpatterns for include("postpress_ai.urls").
- ADD: /normalize/ collision-free path for store_view verifier.
- CHANGE: REMOVE /license/* endpoints from this app-level include to prevent duplicate routes
          in show_urls and to enforce that project-level routing is the single canonical
          surface for licensing under /postpress-ai/license/*.
2025-12-26
- ADD: Stripe webhook route at app-level surface: /stripe/webhook/
       (Stripe is fulfillment-only; WP never talks to Stripe; licensing remains project-level)
2026-01-23
- FIX: ADD translate route at app-level surface: /translate/
       (WP admin-ajax proxy calls /postpress-ai/translate/ and expects JSON)
2026-02-23
- FIX: Register Support routes in the package router so Render live URLConf stops 404'ing.
       Adds /postpress-ai/support/chat/ and /postpress-ai/support/account_status/
- HARDEN: Use getattr() + a 501 fallback so deployments never break if exports are missing.
2026-03-02
- ADD: Campaign issuance route: /postpress-ai/campaign/issue/
       This is a protected endpoint (X-PPA-CAMPAIGN-SECRET) used for GF/Mailchimp issuance.
2026-03-08
- ADD: Remote drafts API routes under /postpress-ai/api/* used by the WP Composer dropdown.
       - /postpress-ai/api/license/sites
       - /postpress-ai/api/remote-drafts/create
       These are hardned with 501 fallbacks if the remote_drafts views are missing.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from django.http import HttpRequest, JsonResponse
from django.urls import path, re_path

from postpress_ai import views as ppa_views
from postpress_ai.views.store import store_view
from postpress_ai.views.stripe_webhook import stripe_webhook

# CHANGED: Import translate endpoint (lives outside views package)
from postpress_ai.views_translate import translate_view


app_name = "postpress_ai"


# --------------------------------------------------------------------------------------
# Support routing hardening (prevents 404s in prod; 501 fallback is acceptable for now)
# --------------------------------------------------------------------------------------


def _support_not_implemented(
    request: HttpRequest, *args: Any, **kwargs: Any
) -> JsonResponse:
    """Fallback handler used ONLY if support view exports are missing."""
    return JsonResponse(
        {
            "ok": False,
            "meta": {
                "error_code": "support_not_implemented",
                "http_status": 501,
                "reason": "Support routes are registered, but view exports are missing.",
            },
        },
        status=501,
    )


_support_chat_view: Optional[Callable[..., Any]] = getattr(
    ppa_views, "support_chat", None
)
_support_account_status_view: Optional[Callable[..., Any]] = getattr(
    ppa_views, "support_account_status", None
)

support_chat_view: Callable[..., Any] = (
    _support_chat_view if callable(_support_chat_view) else _support_not_implemented
)
support_account_status_view: Callable[..., Any] = (
    _support_account_status_view
    if callable(_support_account_status_view)
    else _support_not_implemented
)


# --------------------------------------------------------------------------------------
# Campaign issuance routing hardening (prevents 404s in prod; 501 fallback if missing)
# --------------------------------------------------------------------------------------


def _campaign_not_implemented(
    request: HttpRequest, *args: Any, **kwargs: Any
) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "meta": {
                "error_code": "campaign_not_implemented",
                "http_status": 501,
                "reason": "Campaign issuance route is registered, but view export/import is missing.",
            },
        },
        status=501,
    )


_campaign_issue_view: Optional[Callable[..., Any]] = None
try:
    # Preferred: direct import (does not rely on postpress_ai/views/__init__.py exports)
    from postpress_ai.views.license import (  # type: ignore
        campaign_issue as _campaign_issue_view,
    )
except Exception:
    _campaign_issue_view = getattr(ppa_views, "campaign_issue", None)

campaign_issue_view: Callable[..., Any] = (
    _campaign_issue_view if callable(_campaign_issue_view) else _campaign_not_implemented
)


# --------------------------------------------------------------------------------------
# Remote drafts API routing hardening
# - These power the WP Composer Draft to dropdown + remote draft relay.
# - They MUST NOT 500 if the views are missing; 501 is acceptable.
# --------------------------------------------------------------------------------------


def _remote_api_not_implemented(
    request: HttpRequest, *args: Any, **kwargs: Any
) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "meta": {
                "error_code": "remote_drafts_not_implemented",
                "http_status": 501,
                "reason": "Remote drafts API is registered, but view exports are missing.",
            },
        },
        status=501,
    )


try:
    from postpress_ai.views.remote_drafts import (  # type: ignore
        license_sites as _license_sites_view,
        remote_drafts_create as _remote_drafts_create_view,
    )
except Exception:
    _license_sites_view = None  # type: ignore[assignment]
    _remote_drafts_create_view = None  # type: ignore[assignment]

license_sites_view: Callable[..., Any] = (
    _license_sites_view if callable(_license_sites_view) else _remote_api_not_implemented
)
remote_drafts_create_view: Callable[..., Any] = (
    _remote_drafts_create_view
    if callable(_remote_drafts_create_view)
    else _remote_api_not_implemented
)


urlpatterns = [
    # Readiness / core endpoints (canonical app surface)
    path("health/", ppa_views.health, name="ppa-health"),
    path("version/", ppa_views.version, name="ppa-version"),
    path("preview/", ppa_views.preview, name="ppa-preview"),
    path("store/", ppa_views.store, name="ppa-store"),
    path("generate/", ppa_views.generate, name="ppa-generate"),
    path(
        "preview/debug-model/",
        ppa_views.preview_debug_model,
        name="ppa-preview-debug-model",
    ),

    # Support endpoints (Render must NOT 404 these)
    path("support/chat/", support_chat_view, name="ppa-support-chat"),
    path(
        "support/account_status/",
        support_account_status_view,
        name="ppa-support-account-status",
    ),

    # Translation endpoint (WP expects this exact path)
    path("translate/", translate_view, name="ppa-translate"),

    # Collision-free verifier path -> normalize-only store_view
    path("normalize/", store_view, name="ppa-store-normalize"),

    # Stripe (fulfillment-only)
    path("stripe/webhook/", stripe_webhook, name="ppa-stripe-webhook"),

    # Campaign issuance (protected)
    path("campaign/issue/", campaign_issue_view, name="ppa-campaign-issue"),

    # Remote drafts / multi-site API (used by WP Composer)
    # These are mounted under /postpress-ai/ via agentsuite/urls.py:
    #   POSTPRESS_AI_API_BASE = https://apps.techwithwayne.com/postpress-ai
    #   - GET  {BASE}/api/license/sites[/?]          -> license_sites_view
    #   - POST {BASE}/api/remote-drafts/create[/?]   -> remote_drafts_create_view
    #
    # Optional trailing slash is accepted without redirect (no 301 for POST).
    re_path(
        r"^api/license/sites/?$",
        license_sites_view,
        name="ppa-license-sites-api",
    ),
    re_path(
        r"^api/remote-drafts/create/?$",
        remote_drafts_create_view,
        name="ppa-remote-drafts-create-api",
    ),
]
