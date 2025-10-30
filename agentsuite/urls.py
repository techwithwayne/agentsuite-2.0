"""
CHANGE LOG
----------
2025-10-30
- ADD: Inline /postpress-ai/health/ and /postpress-ai/version/ endpoints placed before include()
       so they resolve first without modifying app files.
- NOTE: Keep endpoints minimal for readiness checks; no extra imports elsewhere.

2025-10-24
- FIX: Map PostPress AI via include("postpress_ai.urls", namespace="postpress_ai") to avoid missing-module errors.
- FIX: Guard optional include("apps.api.urls") so environments without 'apps' do not 500.
"""

from django.contrib import admin
from postpress_ai.views.store import store_view  # CHANGED: PPA direct override

from django.urls import path, include
from django.http import JsonResponse  # ADDED: for health/version JSON responses

# App-level views used here
from webdoctor import views as webdoctor_views
from barista_assistant.views import success_view

app_name = "webdoctor"

# --- Minimal inline endpoints for PostPress AI readiness ------------------------
def ppa_health_view(request):
    """Liveness probe for PostPress AI integration."""
    return JsonResponse({"ok": True})

def ppa_version_view(request):
    """Version probe for PostPress AI; bump string on releases."""
    return JsonResponse({"version": "postpress-ai.v2.1-2025-10-30"})


urlpatterns = [
    # PostPress AI direct store (normalize-only override)
    path("postpress-ai/store/", store_view, name="ppa_store_direct"),  # CHANGED: normalize-only override

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
