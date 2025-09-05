from __future__ import annotations
from django.urls import path
from postpress_ai import views as ppa_views

app_name = "postpress_ai"

urlpatterns = [
    path("health/", ppa_views.health, name="ppa-health"),
    path("version/", ppa_views.version, name="ppa-version"), 
    path("preview/", ppa_views.preview, name="ppa-preview"),
    path("store/", ppa_views.store, name="ppa-store"),
    path("preview/debug-model/", ppa_views.preview_debug_model, name="ppa-preview-debug-model"),
]
