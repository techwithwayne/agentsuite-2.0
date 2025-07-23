from django.db import models
import hashlib

class Conversation(models.Model):
    session_id = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        who = self.name or self.email or "Anonymous"
        return f"{who} - {self.subject or 'No Subject'} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

    class Meta:
        db_table = 'webdoctor_conversations'

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20, choices=[('user', 'User'), ('agent', 'Agent')])
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender.capitalize()} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

    class Meta:
        ordering = ['timestamp']
        db_table = 'webdoctor_messages'

class AgentResponse(models.Model):
    response_text = models.TextField()
    response_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.response_hash = hashlib.sha256(self.response_text.encode()).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_response(cls, response_text):
        response_hash = hashlib.sha256(response_text.encode()).hexdigest()
        return cls.objects.get_or_create(
            response_hash=response_hash,
            defaults={'response_text': response_text}
        )

    class Meta:
        db_table = 'webdoctor_responses'

class UserInteraction(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    issue_description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webdoctor_interactions'

class DiagnosticReport(models.Model):
    user_email = models.EmailField()
    issue_details = models.TextField()
    report_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'webdoctor_reports'
