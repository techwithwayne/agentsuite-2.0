# /home/techwithwayne/agentsuite/postpress_ai/urls.py
"""
PostPress AI — URL routes

CHANGE LOG
----------
2025-10-25 • Fix routing collision by adding a unique path "normalize/" that
             points directly to the normalize-only store_view.               # CHANGED:
- Keep "store/" mapping for final path, but use "normalize/" for verification. # CHANGED:
- app_name retained for namespaced include.                                   # CHANGED:

Notes
-----
Project-level urls.py mounts us at:
    path("postpress-ai/", include("postpress_ai.urls", namespace="postpress_ai"))
Public paths after this change:
    /postpress-ai/store/      -> intended final path (may be shadowed by legacy)
    /postpress-ai/normalize/  -> guaranteed normalize-only path for verification
"""

from __future__ import annotations
from django.urls import path
from .views.store import store_view

# Required for namespaced include(...) in project urls
app_name = "postpress_ai"

urlpatterns = [
    # Final intended path (may be shadowed by a legacy mapping elsewhere)
    path("store/", store_view, name="ppa_store"),

    # Collision-free verifier path -> always our normalize-only view
    path("normalize/", store_view, name="ppa_store_normalize"),
]
