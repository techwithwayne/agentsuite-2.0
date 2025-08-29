# /home/techwithwayne/agentsuite/postpress_ai/urls/routes_legacy.py
"""
CHANGE LOG
----------
2025-08-16
- FIX (circular import): Removed any import/alias of the canonical package router             # CHANGED:
  (e.g., `from postpress_ai import urls as canonical`) and stopped re-exporting               # CHANGED:
  `canonical.urlpatterns`. This file now declares its own patterns that point                 # CHANGED:
  directly to the public surface `postpress_ai.views`.                                        # CHANGED:
- COMPAT: Endpoint list mirrors the canonical router so legacy includes continue              # CHANGED:
  to work without altering contracts.                                                         # CHANGED:
"""

from __future__ import annotations  # CHANGED:

from django.urls import path  # CHANGED:

# Import the *public surface* only. Do NOT import postpress_ai.urls here,                     # CHANGED:
# because the canonical package router (`postpress_ai/urls/__init__.py`)                      # CHANGED:
# includes this file for backward compatibility — importing it back would cause a loop.       # CHANGED:
from postpress_ai import views as ppa_views  # CHANGED:

app_name = "postpress_ai"  # CHANGED:

# Legacy URL patterns — defined locally to avoid circular imports.                            # CHANGED:
urlpatterns = [  # CHANGED:
    path("health/", ppa_views.health, name="ppa-health"),  # CHANGED:
    path("version/", ppa_views.version, name="ppa-version"),  # CHANGED:
    path("preview/", ppa_views.preview, name="ppa-preview"),  # CHANGED:
    path("store/", ppa_views.store, name="ppa-store"),  # CHANGED:
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),  # CHANGED:
]  # CHANGED:
