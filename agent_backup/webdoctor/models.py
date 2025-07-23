# webdoctor/admin.py

from django.contrib import admin
from .models import Conversation

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'email', 
        'subject', 
        'timestamp', 
        'short_user_message', 
        'short_agent_response'
    )
    search_fields = (
        'name', 
        'email', 
        'subject', 
        'user_message', 
        'agent_response'
    )
    list_filter = ('timestamp',)
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

    def short_user_message(self, obj):
        return (obj.user_message[:50] + "...") if len(obj.user_message) > 50 else obj.user_message
    short_user_message.short_description = "User Message"

    def short_agent_response(self, obj):
        return (obj.agent_response[:50] + "...") if len(obj.agent_response) > 50 else obj.agent_response
    short_agent_response.short_description = "Agent Response"
