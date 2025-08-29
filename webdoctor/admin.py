# webdoctor/admin.py
# Correct admin configuration using actual field names

from django.contrib import admin
from .models import Conversation, Message, UserInteraction

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['sender', 'content', 'created_at']
    fields = ['sender', 'content', 'created_at']

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', 'created_at']
    list_filter = ['sender', 'created_at', 'is_active']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    search_fields = ['content', 'sender']

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'session_id', 'name', 'email', 'subject', 'created_at']
    list_filter = ['is_active', 'created_at']
    readonly_fields = ['session_id', 'created_at', 'updated_at']
    ordering = ['-created_at']
    inlines = [MessageInline]
    search_fields = ['name', 'email', 'subject', 'session_id']

@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'ip_address', 'created_at']
    list_filter = ['is_active', 'created_at']
    ordering = ['-created_at']
    readonly_fields = ['ip_address', 'user_agent', 'created_at', 'updated_at']
    search_fields = ['name', 'email', 'issue_description']
    
    # Show issue description in a more readable format
    def get_readonly_fields(self, request, obj=None):
        if obj:  # Editing an existing object
            return self.readonly_fields + ['issue_description']
        return self.readonly_fields