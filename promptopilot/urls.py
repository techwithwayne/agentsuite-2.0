# promptopilot/urls.py

from django.urls import path
from . import views



urlpatterns = [
    path("ad-builder/", views.ad_builder_page, name="ad_builder_page"),
    path("widget-frame/", views.widget_frame_page, name="widget_frame_page"),
    path("api/ad-builder/", views.ad_builder_api, name="ad_builder_api"),
    path("history/", views.prompt_history_view, name="prompt_history"),
]
