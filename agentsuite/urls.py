"""
CHANGE LOG
----------
2025-08-19
- FIX: Remove the earlier duplicate/legacy include for `/postpress-ai/` that pointed
  to `postpress_ai.urls.routes_legacy`. Because Django resolves top-to-bottom, that
  entry shadowed the canonical routes and forced live traffic into legacy views.      # CHANGED:
- FIX: Restore the correct Personal Mentor route at `/personal-mentor/`.              # CHANGED:
- KEEP: Single canonical mapping for PostPress AI: include("postpress_ai.urls", ...). # CHANGED:
- SAFETY: No other routes changed. Comments expanded to explain resolution order.     # CHANGED:

Notes:
- Leaving a commented "tombstone" line to document the removed legacy include so
  future diffs and audits are clear on intent.                                         # CHANGED:
"""

from django.contrib import admin
from django.urls import path, include
from webdoctor import views
from barista_assistant.views import success_view

app_name = 'webdoctor'

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # Webdoctor + tools
    path("agent/", include("webdoctor.urls")),
    path("webdoctor/", views.webdoctor_home, name="webdoctor_home"),
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
    path("personal-mentor/", include("personal_mentor.urls", namespace="personal_mentor")),  # CHANGED:

    # Debug views
    path("debug_conversation/", views.debug_conversation, name="debug_conversation"),
    path("reset_conversation/", views.reset_conversation, name="reset_conversation"),

    # === PostPress AI (canonical include) =========================================
    # IMPORTANT:
    # Django resolves in order. We must have ONLY ONE mapping for '/postpress-ai/' and it
    # must point to the canonical package URLConf so endpoints resolve to 'postpress_ai.views'.
    # Having an earlier 'routes_legacy' include here would shadow this mapping.
    path("postpress-ai/", include("postpress_ai.urls", namespace="postpress_ai")),  # CHANGED:

    # --- Legacy Tombstone (for audit history only; do NOT uncomment) ---------------  # CHANGED:
    # Previously (bug):                                                               # CHANGED:
    # path("postpress-ai/", include("postpress_ai.urls.routes_legacy",               # CHANGED:
    #      namespace="postpress_ai")),  # would have shadowed the canonical include   # CHANGED:

    path("api/therapylib/", include("therapylib.urls")),
    path("humancapital/", include(("humancapital.urls", "humancapital"), namespace="humancapital")),
]
