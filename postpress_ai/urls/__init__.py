# /home/techwithwayne/agentsuite/postpress_ai/urls/__init__.py
"""
PostPress AI — URL routes (package router)

CHANGE LOG
----------
2025-12-24
- FIX: Remove invalid import 'from .urls import ...' (no postpress_ai/urls/urls.py exists).  # CHANGED:
- KEEP: Provide deterministic urlpatterns for include("postpress_ai.urls").                  # CHANGED:
- ADD: /license/* endpoints here too (project-level routes still take precedence).           # CHANGED:
- ADD: /normalize/ collision-free path for store_view verifier.                              # CHANGED:
"""

from __future__ import annotations

from django.urls import path  # CHANGED:

from postpress_ai import views as ppa_views  # CHANGED:
from postpress_ai.views.store import store_view  # CHANGED:
from postpress_ai.views.license import (  # CHANGED:
    license_activate,  # CHANGED:
    license_verify,  # CHANGED:
    license_deactivate,  # CHANGED:
)

app_name = "postpress_ai"

urlpatterns = [
    # Readiness / core endpoints (canonical app surface)
    path("health/", ppa_views.health, name="ppa-health"),
    path("version/", ppa_views.version, name="ppa-version"),
    path("preview/", ppa_views.preview, name="ppa-preview"),
    path("store/", ppa_views.store, name="ppa-store"),
    path("generate/", ppa_views.generate, name="ppa-generate"),
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),

    # Collision-free verifier path -> normalize-only store_view
    path("normalize/", store_view, name="ppa-store-normalize"),  # CHANGED:

    # Licensing endpoints (Django authoritative; project-level routes still override precedence)  # CHANGED:
    path("license/activate/", license_activate, name="license_activate"),  # CHANGED:
    path("license/verify/", license_verify, name="license_verify"),  # CHANGED:
    path("license/deactivate/", license_deactivate, name="license_deactivate"),  # CHANGED:
]
