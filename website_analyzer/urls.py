from django.urls import path
from .views import home, analyze_api, fetch_diagnostics



urlpatterns = [
    path('', home, name='home'),
    path("api/analyze/", analyze_api, name="analyze_api"),
    path("api/fetch-diagnostics/", fetch_diagnostics, name="fetch_diagnostics"),
]
