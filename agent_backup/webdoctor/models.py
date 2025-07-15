from django.db import models

class Conversation(models.Model):
    session_id = models.CharField(max_length=255, blank=True, null=True)  # <-- Added for memory
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    user_message = models.TextField()
    agent_response = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        who = self.name or self.email or "Anonymous"
        return f"{who} - {self.subject or 'No Subject'} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
