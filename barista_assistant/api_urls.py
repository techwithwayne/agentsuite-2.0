from django.urls import path, include

urlpatterns = [
    path('', include('barista_assistant.menu.urls')),
    path('', include('barista_assistant.orders.urls')),
]