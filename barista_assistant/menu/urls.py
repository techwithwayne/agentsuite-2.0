from django.urls import path
from .views import MenuItemListView, barista_assistant_test

urlpatterns = [
    path('menu/', MenuItemListView.as_view(), name='menu-list'),
    path('barista-assistant-test/', barista_assistant_test, name='barista-assistant-test'),
]