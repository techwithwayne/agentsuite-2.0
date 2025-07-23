from django.urls import path
from . import views

urlpatterns = [
    path('', views.webdoctor_home, name='webdoctor_home'),
    path('chat/', views.chat_widget, name='chat_widget'),
    path('handle_message/', views.handle_message, name='handle_message'),
    path('submit_form/', views.submit_form, name='submit_form'),
]
