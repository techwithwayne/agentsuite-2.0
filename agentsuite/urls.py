# /home/techwithwayne/agentsuite/agentsuite/urls.py
"""
CHANGE LOG
----------
2025-12-24
- ADD: Project-level /postpress-ai/license/* endpoints before include() for precedence.  # CHANGED:
       activate/verify/deactivate → postpress_ai.views.license (Django authoritative). # CHANGED:
- ADD: Project-level /postpress-ai/license/debug-auth/ endpoint before include() for precedence.  # CHANGED:
       debug-auth → postpress_ai.views.debug_model.license_debug_auth (safe booleans only).       # CHANGED:
- FIX: Normalize change markers in this file to use '# CHANGED:' consistently.  # CHANGED:

2025-12-26
- ADD: Project-level /postpress-ai/stripe/webhook/ endpoint before include() for precedence.  # CHANGED:
       Stripe is fulfillment-only (payment -> issue key), WP never talks to Stripe.            # CHANGED:

2025-11-10
- ADD: Root-level aliases /preview/ and /store/ → canonical postpress_ai views.          # CHANGED:
- KEEP: Direct /postpress-ai/store/ override precedence and /postpress-ai include.       # CHANGED:

2025-10-30
- ADD: Inline /postpress-ai/health/ and /postpress-ai/version/ endpoints placed before include()
       so they resolve first without modifying app files.
- NOTE: Keep endpoints minimal for readiness checks; no extra imports elsewhere.

2025-10-24
- FIX: Map PostPress AI via include("postpress_ai.urls", namespace="postpress_ai") to avoid missing-module errors.
- FIX: Guard optional include("apps.api.urls") so environments without 'apps' do not 500.
"""

from django.contrib import admin
from django.http import JsonResponse  # CHANGED: for health/version JSON responses
from django.urls import path, include

from postpress_ai import views as ppa_views  # CHANGED: for root-level aliases
from postpress_ai.views.store import store_view  # CHANGED: PPA direct override

# Licensing endpoints (project-level precedence)  # CHANGED:
from postpress_ai.views.license import (  # CHANGED:
    license_activate,  # CHANGED:
    license_verify,  # CHANGED:
    license_deactivate,  # CHANGED:
)

# Debug auth endpoint (project-level precedence)  # CHANGED:
from postpress_ai.views.debug_model import license_debug_auth  # CHANGED:

# Stripe webhook endpoint (project-level precedence; fulfillment-only)  # CHANGED:
from postpress_ai.views.stripe_webhook import stripe_webhook  # CHANGED:

# App-level views used here
from webdoctor import views as webdoctor_views
from barista_assistant.views import success_view

app_name = "webdoctor"

# --- Minimal inline endpoints for PostPress AI readiness ------------------------
def ppa_health_view(request):  # CHANGED:
    """Liveness probe for PostPress AI integration."""  # CHANGED:
    return JsonResponse({"ok": True})  # CHANGED:


def ppa_version_view(request):  # CHANGED:
    """Version probe for PostPress AI; bump string on releases."""  # CHANGED:
    return JsonResponse({"version": "postpress-ai.v2.1-2025-10-30"})  # CHANGED:


urlpatterns = [
    # Root-level aliases to canonical PPA views (in addition to the prefixed include)  # CHANGED:
    path("preview/", ppa_views.preview, name="ppa-preview-root"),  # CHANGED:
    path("store/", ppa_views.store, name="ppa-store-root"),  # CHANGED:

    # PostPress AI direct store (normalize-only override; precedence over include)
    path("postpress-ai/store/", store_view, name="ppa_store_direct"),

    # PostPress AI licensing endpoints (placed BEFORE include to take precedence)  # CHANGED:
    path("postpress-ai/license/activate/", license_activate, name="ppa_license_activate"),  # CHANGED:
    path("postpress-ai/license/verify/", license_verify, name="ppa_license_verify"),  # CHANGED:
    path("postpress-ai/license/deactivate/", license_deactivate, name="ppa_license_deactivate"),  # CHANGED:

    # PostPress AI debug auth endpoint (placed BEFORE include to take precedence)  # CHANGED:
    path("postpress-ai/license/debug-auth/", license_debug_auth, name="ppa_license_debug_auth"),  # CHANGED:

    # PostPress AI Stripe webhook endpoint (placed BEFORE include to take precedence)  # CHANGED:
    path("postpress-ai/stripe/webhook/", stripe_webhook, name="ppa_stripe_webhook"),  # CHANGED:

    # PostPress AI readiness endpoints (placed BEFORE include to take precedence)
    path("postpress-ai/health/", ppa_health_view, name="ppa_health"),
    path("postpress-ai/version/", ppa_version_view, name="ppa_version"),

    # Admin
    path("admin/", admin.site.urls),

    # Webdoctor + tools
    path("agent/", include("webdoctor.urls")),
    path("webdoctor/", webdoctor_views.webdoctor_home, name="webdoctor_home"),
    path("tools/", include("promptopilot.urls")),

    # Website Analyzer
    path("website-analyzer/", include("website_analyzer.urls")),

    # Barista Assistant + API
    path("barista-assistant/", include("barista_assistant.urls")),
    path("api/", include("barista_assistant.api_urls")),
    path("api/menu/", include("barista_assistant.menu.urls")),
    path("success/", success_view, name="stripe-success"),

    # Content Strategy
    path("content-strategy/", include("content_strategy_generator_agent.urls")),

    # Personal Mentor
    path("personal-mentor/", include("personal_mentor.urls", namespace="personal_mentor")),

    # Debug views
    path("debug_conversation/", webdoctor_views.debug_conversation, name="debug_conversation"),
    path("reset_conversation/", webdoctor_views.reset_conversation, name="reset_conversation"),

    # === PostPress AI (canonical include) =========================================
    # NOTE: postpress_ai/urls.py re-exports routes_legacy; do NOT include routes_legacy directly.
    path("postpress-ai/", include("postpress_ai.urls", namespace="postpress_ai")),

    # Additional app routes
    path("api/therapylib/", include("therapylib.urls")),
    path("humancapital/", include("humancapital.urls", namespace="humancapital")),
]

# === Optional/Monorepo routes (guarded) ============================================
# Some deployments do not have the 'apps' package checked out; include only if importable.
try:
    import importlib
    importlib.import_module("apps.api.urls")
except ModuleNotFoundError:
    import sys
    sys.stderr.write("[urls] Optional 'apps.api.urls' not present; skipping /reclaimr/ route\n")
else:
    urlpatterns.append(path("reclaimr/", include("apps.api.urls")))
