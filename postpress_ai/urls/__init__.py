# /home/techwithwayne/agentsuite/postpress_ai/urls/__init__.py
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
"""
from __future__ import annotations

from django.urls import path  # CHANGED:

from postpress_ai import views as ppa_views  # CHANGED:
from postpress_ai.views.store import store_view  # CHANGED:
from postpress_ai.views.stripe_webhook import stripe_webhook  # CHANGED:

# CHANGED: Import translate endpoint (lives outside views package)
from postpress_ai.views_translate import translate_view  # CHANGED:

app_name = "postpress_ai"

urlpatterns = [
    # Readiness / core endpoints (canonical app surface)
    path("health/", ppa_views.health, name="ppa-health"),
    path("version/", ppa_views.version, name="ppa-version"),
    path("preview/", ppa_views.preview, name="ppa-preview"),
    path("store/", ppa_views.store, name="ppa-store"),
    path("generate/", ppa_views.generate, name="ppa-generate"),
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),

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
