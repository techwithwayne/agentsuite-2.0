from __future__ import annotations

from django.urls import re_path  # CHANGED:
from postpress_ai import views as ppa_views

app_name = "postpress_ai"

urlpatterns = [
    # Accept both /x and /x/ (prevents 301 from APPEND_SLASH + CommonMiddleware).  # CHANGED:
    re_path(r"health/?$", ppa_views.health, name="ppa-health"),  # CHANGED:
    re_path(r"version/?$", ppa_views.version, name="ppa-version"),  # CHANGED:
    re_path(r"preview/?$", ppa_views.preview, name="ppa-preview"),  # CHANGED:
    re_path(r"store/?$", ppa_views.store, name="ppa-store"),  # CHANGED:
    re_path(r"preview/debug-model/?$", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),  # CHANGED:
]