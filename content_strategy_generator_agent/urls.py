from django.urls import path
from . import views

urlpatterns = [
    path('', views.generate_strategy, name='generate_strategy'),
]
