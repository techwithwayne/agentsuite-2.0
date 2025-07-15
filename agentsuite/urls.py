from django.contrib import admin
from django.urls import path, include
from barista_assistant.orders.views import stripe_success_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path('webdoctor/', include('webdoctor.urls')),
    path('website-analyzer/', include('website_analyzer.urls')),
    path('barista-assistant/', include('barista_assistant.urls')),
    path('content-strategy/', include('content_strategy_generator_agent.urls')),
    path('api/', include('barista_assistant.api_urls')),
    path("success/", stripe_success_view, name="stripe-success"),
]
