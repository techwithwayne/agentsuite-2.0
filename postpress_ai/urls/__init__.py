# /home/techwithwayne/agentsuite/postpress_ai/urls/__init__.py
"""
CHANGE LOG
----------
2025-08-16
- CLEANUP (canonical routing): Removed redundant include("postpress_ai.urls.routes_legacy")     # CHANGED:
  to avoid duplicate URL patterns and reverse-name collisions. Legacy routes remain            # CHANGED:
  available via explicit include("postpress_ai.urls.routes_legacy") wherever needed.           # CHANGED:
- KEEP: Canonical endpoints map directly to postpress_ai.views (public surface).               # CHANGED:

2025-08-16
- NEW FILE (canonical routing): Provide the canonical URLConf as a package
  module (`postpress_ai.urls`) exposing health/, version/, preview/, store/,
  and preview/debug-model/.
"""

from __future__ import annotations  # CHANGED:

from django.urls import path  # CHANGED:

# Public surface: re-exported views live in postpress_ai.views                                # CHANGED:
from postpress_ai import views as ppa_views  # CHANGED:

app_name = "postpress_ai"  # CHANGED:

# Canonical endpoints → always point at the public surface in postpress_ai.views              # CHANGED:
urlpatterns = [  # CHANGED:
    path("health/", ppa_views.health, name="ppa-health"),  # CHANGED:
    path("version/", ppa_views.version, name="ppa-version"),  # CHANGED:
    path("preview/", ppa_views.preview, name="ppa-preview"),  # CHANGED:
    path("store/", ppa_views.store, name="ppa-store"),  # CHANGED:
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),  # CHANGED:
]  # CHANGED:
