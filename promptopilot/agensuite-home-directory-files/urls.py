from django.contrib import admin
from django.urls import path, include
from webdoctor import views
from barista_assistant.views import success_view

urlpatterns = [
    path("admin/", admin.site.urls),
    
    path("agent/", include("webdoctor.urls")),
    path('webdoctor/', include('webdoctor.urls')),
    path('webdoctor/', views.webdoctor_home, name='webdoctor_home'),
    
    path("coach/", include("personal_coach.urls")),
    
    path("tools/", include("promptopilot.urls")),
    path("promptopilot/", include("promptopilot.urls")),

    path('website-analyzer/', include('website_analyzer.urls')),
    
    path('barista-assistant/', include('barista_assistant.urls')),
    path('api/', include('barista_assistant.api_urls')),
    path('api/menu/', include('barista_assistant.menu.urls')),
    path("success/", success_view, name="stripe-success"),
    
    path('content-strategy/', include('content_strategy_generator_agent.urls')),
    
]
