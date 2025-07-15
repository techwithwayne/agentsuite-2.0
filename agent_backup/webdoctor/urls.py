from django.urls import path
from .views import chat_with_agent, chatbot_iframe_view

urlpatterns = [
    path("ask/", chat_with_agent, name="ask-agent"),
    path('widget-frame/', chatbot_iframe_view, name='chatbot_widget_frame'),
]
