from django.urls import path
from . import views
from . import views_auth

app_name = "personal_mentor"

urlpatterns = [
    path("", views.chat_view, name="chat"),

    # Chat API (existing)
    path("api/send/", views.api_send, name="api_send"),
    path("api/reset/", views.api_reset, name="api_reset"),
    path("api/health/", views.api_health, name="api_health"),

    # Auth API
    path("auth/register/", views_auth.start_registration, name="start_registration"),
    path("auth/confirm/", views_auth.confirm_code, name="confirm_code"),
    path("auth/login/", views_auth.login_user, name="login_user"),
    path("auth/resend/", views_auth.resend_code, name="resend_code"),
]
