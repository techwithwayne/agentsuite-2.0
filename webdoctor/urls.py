from django.urls import path
from . import views

urlpatterns = [
    # ✅ Main pages
    path('', views.webdoctor_home, name='webdoctor_home'),
    path('chat/', views.chat_widget, name='chat_widget'),
    
    # ✅ Core API endpoints
    path('handle_message/', views.handle_message, name='handle_message'),
    path('ask/', views.handle_message, name='ask_agent'),  # Backward compatibility
    path('submit_form/', views.submit_form, name='submit_form'),
    
    # ✅ NEW: Conversation reset endpoint
    path('reset_conversation/', views.reset_conversation, name='reset_conversation'),
    
    # ✅ Tool API endpoints
    path('send_email_diagnostic/', views.send_email_diagnostic, name='send_email_diagnostic'),
    path('recommend_fixes/', views.recommend_fixes, name='recommend_fixes'), 
    path('measure_speed/', views.measure_speed, name='measure_speed'),
    path('get_plugin_list/', views.get_plugin_list, name='get_plugin_list'),
    
    # ✅ Debug endpoint (if needed)
    path('debug_conversation/', views.debug_conversation, name='debug_conversation'),
]