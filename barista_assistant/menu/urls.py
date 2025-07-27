from django.urls import path
from .views import MenuItemListView, seed_menu

urlpatterns = [
    path('', MenuItemListView.as_view(), name='menu-list'),
    path('seed/', seed_menu, name='menu-seed'),
]