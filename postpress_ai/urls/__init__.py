"""
PostPress AI — URL routes (package router)

CHANGE LOG
----------
2025-12-24
- FIX: Remove invalid import 'from .urls import ...' (no postpress_ai/urls/urls.py exists).  # CHANGED:
- KEEP: Provide deterministic urlpatterns for include("postpress_ai.urls").                  # CHANGED:
- ADD: /normalize/ collision-free path for store_view verifier.                              # CHANGED:
- CHANGE: REMOVE /license/* endpoints from this app-level include to prevent duplicate routes # CHANGED:
          in show_urls and to enforce that project-level routing is the single canonical      # CHANGED:
          surface for licensing under /postpress-ai/license/*.                                # CHANGED:
2025-12-26
- ADD: Stripe webhook route at app-level surface: /stripe/webhook/                            # CHANGED:
       (Stripe is fulfillment-only; WP never talks to Stripe; licensing remains project-level)# CHANGED:
2026-01-23
- FIX: ADD translate route at app-level surface: /translate/                                  # CHANGED:
       (WP admin-ajax proxy calls /postpress-ai/translate/ and expects JSON)                  # CHANGED:
2026-02-23
- FIX: Register Support routes in the package router so Render live URLConf stops 404'ing.    # CHANGED:
       Adds /postpress-ai/support/chat/ and /postpress-ai/support/account_status/             # CHANGED:
- HARDEN: Use getattr() + a 501 fallback so deployments never break if exports are missing.   # CHANGED:
"""
from __future__ import annotations

from typing import Any, Callable, Optional  # CHANGED:

from django.http import HttpRequest, JsonResponse  # CHANGED:
from django.urls import path  # CHANGED:

from postpress_ai import views as ppa_views  # CHANGED:
from postpress_ai.views.store import store_view  # CHANGED:
from postpress_ai.views.stripe_webhook import stripe_webhook  # CHANGED:

# CHANGED: Import translate endpoint (lives outside views package)
from postpress_ai.views_translate import translate_view  # CHANGED:

app_name = "postpress_ai"


# --------------------------------------------------------------------------------------
# Support routing hardening (prevents 404s in prod; 501 fallback is acceptable for now)
# --------------------------------------------------------------------------------------
def _support_not_implemented(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:  # CHANGED:
    """
    Fallback handler used ONLY if support view exports are missing.
    This ensures routes register and return 501 (acceptable) instead of 404.  # CHANGED:
    """
    return JsonResponse(  # CHANGED:
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


# CHANGED: Prefer exported views from postpress_ai.views (matches your scaffold + exports intent).
_support_chat_view: Optional[Callable[..., Any]] = getattr(ppa_views, "support_chat", None)  # CHANGED:
_support_account_status_view: Optional[Callable[..., Any]] = getattr(  # CHANGED:
    ppa_views, "support_account_status", None
)

# CHANGED: Safe fallback so we never break deployments with AttributeError/ImportError.
support_chat_view: Callable[..., Any] = (  # CHANGED:
    _support_chat_view if callable(_support_chat_view) else _support_not_implemented
)
support_account_status_view: Callable[..., Any] = (  # CHANGED:
    _support_account_status_view if callable(_support_account_status_view) else _support_not_implemented
)


urlpatterns = [
    # Readiness / core endpoints (canonical app surface)
    path("health/", ppa_views.health, name="ppa-health"),
    path("version/", ppa_views.version, name="ppa-version"),
    path("preview/", ppa_views.preview, name="ppa-preview"),
    path("store/", ppa_views.store, name="ppa-store"),
    path("generate/", ppa_views.generate, name="ppa-generate"),
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),

    # CHANGED: Support endpoints (Render must NOT 404 these)
    path("support/chat/", support_chat_view, name="ppa-support-chat"),  # CHANGED:
    path("support/account_status/", support_account_status_view, name="ppa-support-account-status"),  # CHANGED:

    # CHANGED: Translation endpoint (WP expects this exact path)
    path("translate/", translate_view, name="ppa-translate"),  # CHANGED:

    # Collision-free verifier path -> normalize-only store_view
    path("normalize/", store_view, name="ppa-store-normalize"),  # CHANGED:

    # Stripe (fulfillment-only)
    path("stripe/webhook/", stripe_webhook, name="ppa-stripe-webhook"),  # CHANGED:

    # NOTE (LOCKED):
    # Licensing routes are intentionally NOT included here.                                     # CHANGED:
    # They are project-level only in agentsuite/urls.py under:                                  # CHANGED:
    #   /postpress-ai/license/activate/                                                         # CHANGED:
    #   /postpress-ai/license/verify/                                                           # CHANGED:
    #   /postpress-ai/license/deactivate/                                                       # CHANGED:
    #   /postpress-ai/license/debug-auth/                                                       # CHANGED:
    # This prevents duplicate route listings and keeps the authoritative surface centralized.   # CHANGED:
]