from django.urls import path
from . import views

urlpatterns = [
    path('', views.webdoctor_home, name='webdoctor_home'),
    path("widget-frame/", views.widget_frame, name="webdoctor-widget-frame"),
    path('chat/', views.chat_widget, name='chat_widget'),
    path('handle_message/', views.handle_message, name='handle_message'),
    path('submit_form/', views.submit_form, name='submit_form'),
]
