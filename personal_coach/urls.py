# urls.py
# Defines endpoints for the AI widget

from django.urls import path
from personal_coach import views

urlpatterns = [
    path("", views.chat_widget, name="personal_ai_chat"),
    path("send/", views.handle_message, name="personal_ai_send"),
]
