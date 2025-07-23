from django.contrib import admin
from webdoctor.models import UserInteraction, AgentResponse, DiagnosticReport
from webdoctor.models import Conversation, Message

@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'issue_description', 'timestamp')
    search_fields = ('email', 'issue_description')

@admin.register(AgentResponse)
class AgentResponseAdmin(admin.ModelAdmin):
    list_display = ('response_text', 'created_at')
    search_fields = ('response_text',)

@admin.register(DiagnosticReport)
class DiagnosticReportAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'created_at')
    search_fields = ('user_email', 'report_content')
    
class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender', 'content', 'timestamp')
    can_delete = False
    show_change_link = False

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'timestamp')
    search_fields = ('name', 'email', 'subject')
    list_filter = ('timestamp',)
    ordering = ('-timestamp',)
    inlines = [MessageInline]
    readonly_fields = ('name', 'email', 'subject', 'timestamp')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'sender', 'timestamp', 'short_content')
    search_fields = ('conversation__email', 'content')
    list_filter = ('sender', 'timestamp')
    ordering = ('-timestamp',)

    def short_content(self, obj):
        return obj.content[:60] + "..." if len(obj.content) > 60 else obj.content
    short_content.short_description = "Content"
