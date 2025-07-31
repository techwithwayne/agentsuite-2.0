# webdoctor/models.py - Enhanced Database Models
from django.db import models
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
import hashlib
import logging

logger = logging.getLogger('webdoctor')

class BaseModel(models.Model):
    """✅ Base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        abstract = True

class Conversation(BaseModel):
    """✅ Enhanced conversation model"""
    session_id = models.CharField(max_length=255, db_index=True, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(validators=[EmailValidator()], blank=True, null=True, db_index=True)
    subject = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        identifier = self.name or self.email or self.session_id or "Anonymous"
        return f"{identifier} - {self.subject or 'No Subject'} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
    
    @transaction.atomic
    def add_message(self, sender, content):
        """✅ Safe message addition"""
        return Message.objects.create(
            conversation=self,
            sender=sender,
            content=content[:2000]  # Limit message length
        )
    
    @property
    def message_count(self):
        return self.messages.count()
    
    class Meta:
        db_table = 'webdoctor_conversations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'created_at']),
            models.Index(fields=['session_id', 'created_at']),
        ]

class Message(BaseModel):
    """✅ Enhanced message model"""
    SENDER_CHOICES = [
        ('user', 'User'),
        ('agent', 'Agent'),
        ('system', 'System')
    ]
    
    conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES, db_index=True)
    content = models.TextField(max_length=2000)  # ✅ Limit content length
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_sender_display()} - {self.content[:50]}..." if len(self.content) > 50 else f"{self.get_sender_display()} - {self.content}"
    
    def clean(self):
        """✅ Validate message content"""
        if not self.content.strip():
            raise ValidationError("Message content cannot be empty")
        
        # Basic content filtering
        prohibited_words = ['<script', 'javascript:', 'eval(', 'onclick=']
        content_lower = self.content.lower()
        if any(word in content_lower for word in prohibited_words):
            raise ValidationError("Message contains prohibited content")
    
    class Meta:
        db_table = 'webdoctor_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
        ]

class AgentResponse(BaseModel):
    """✅ Enhanced agent response model"""
    response_text = models.TextField(max_length=5000)
    response_hash = models.CharField(max_length=64, unique=True, db_index=True)
    usage_count = models.PositiveIntegerField(default=0)  # ✅ Track reuse
    
    def save(self, *args, **kwargs):
        if not self.response_hash:
            self.response_hash = hashlib.sha256(self.response_text.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)
    
    @classmethod
    @transaction.atomic
    def get_or_create_response(cls, response_text):
        """✅ Thread-safe response creation"""
        response_hash = hashlib.sha256(response_text.encode('utf-8')).hexdigest()
        
        response, created = cls.objects.get_or_create(
            response_hash=response_hash,
            defaults={'response_text': response_text}
        )
        
        if not created:
            # ✅ Increment usage counter
            cls.objects.filter(id=response.id).update(
                usage_count=models.F('usage_count') + 1
            )
            response.refresh_from_db()
        
        return response, created
    
    class Meta:
        db_table = 'webdoctor_responses'
        ordering = ['-created_at']

class UserInteraction(BaseModel):
    """✅ Enhanced user interaction model"""
    name = models.CharField(max_length=100, db_index=True)
    email = models.EmailField(validators=[EmailValidator()], db_index=True)
    issue_description = models.TextField(max_length=1000)
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # ✅ Track IP for analytics
    user_agent = models.TextField(blank=True, null=True)  # ✅ Track browser info
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.email}) - {self.issue_description[:50]}..."
    
    def clean(self):
        """✅ Validate interaction data"""
        if not self.name.strip():
            raise ValidationError("Name cannot be empty")
        if not self.issue_description.strip():
            raise ValidationError("Issue description cannot be empty")
    
    class Meta:
        db_table = 'webdoctor_interactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'created_at']),
            models.Index(fields=['created_at']),
        ]

class DiagnosticReport(BaseModel):
    """✅ Enhanced diagnostic report model"""
    user_interaction = models.ForeignKey(
        UserInteraction, 
        on_delete=models.CASCADE,
        related_name='reports',
        null=True, 
        blank=True
    )  # ✅ Link to interaction
    user_email = models.EmailField(validators=[EmailValidator()], db_index=True)
    issue_details = models.TextField(max_length=1000)
    report_content = models.TextField(max_length=5000)
    email_sent = models.BooleanField(default=False, db_index=True)  # ✅ Track email status
    email_sent_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        status = "✅ Sent" if self.email_sent else "⏳ Pending"
        return f"Report for {self.user_email} - {status}"
    
    @transaction.atomic
    def mark_email_sent(self):
        """✅ Mark email as sent"""
        self.email_sent = True
        self.email_sent_at = timezone.now()
        self.save(update_fields=['email_sent', 'email_sent_at'])
        logger.info(f"Email sent for report {self.id} to {self.user_email}")
    
    class Meta:
        db_table = 'webdoctor_reports'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_email', 'created_at']),
            models.Index(fields=['email_sent', 'created_at']),
        ]