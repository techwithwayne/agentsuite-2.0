from django.contrib import admin
from django.utils.html import format_html
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user_email", "user_first_name", "verification_status", "verified_at", "code_sent_at")
    list_select_related = ("user",)
    readonly_fields = ("verification_status", "verification_code", "code_sent_at", "verified_at", "last_resend_at", "created_at")
    search_fields = ("user__email", "user__first_name")
    ordering = ("-verified_at", "-code_sent_at")

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    def user_first_name(self, obj):
        return obj.user.first_name
    user_first_name.short_description = "First name"

    def verification_status(self, obj):
        if obj.verified_at:
            return format_html('<span style="color: #16a34a;">Verified</span>')
        if obj.verification_code and obj.code_sent_at:
            return format_html('<span style="color: #f59e0b;">Pending</span>')
        return format_html('<span style="color: #ef4444;">Not sent</span>')
    verification_status.short_description = "Status"
