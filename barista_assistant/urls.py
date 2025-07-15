from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name='barista_home'),
    path('success/', views.success_view, name='barista_success'),
    path('cancel/', views.cancel_view, name='barista_cancel'),
    path('api/', include('barista_assistant.api_urls')),
]
