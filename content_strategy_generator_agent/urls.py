# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_strategy, name='generate_strategy'),
    path('json/', views.generate_strategy_json, name='generate_strategy_json'),
]
