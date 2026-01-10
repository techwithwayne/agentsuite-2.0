# /home/techwithwayne/agentsuite/postpress_ai/models/email_log.py

"""
PostPress AI — Email Log model
Path: postpress_ai/models/email_log.py

Purpose:
- Track customer-facing emails (especially license key delivery).
- Provide admin-visible proof: what was sent, when, to whom, and status.
- Store provider message IDs (SendGrid) when available.
- Keep payload snippets minimal (avoid storing full license keys).

Design rules:
- NEVER store full license key in EmailLog (only last4 or masked).
- Link to Customer when possible.

CHANGE LOG
- 2026-01-10: Create EmailLog model for Command Center visibility.  # CHANGED:
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

try:
    # Optional (safe) dependency: if Customer model exists, link it
    from .customer import Customer
except Exception:
    Customer = None  # type: ignore


class EmailLog(models.Model):
    """
    Record of an attempted outgoing email.

    This is not meant to replace SendGrid Activity — it’s your internal,
    business-friendly audit trail.
    """

    # Link to customer when available.
    # If Customer import failed (shouldn't), we still allow logs without FK.
    customer = models.ForeignKey(  # CHANGED:
        "postpress_ai.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )

    # Core routing
    to_email = models.EmailField()  # CHANGED:
    subject = models.CharField(max_length=255)  # CHANGED:

    # What kind of email was this?
    TYPE_LICENSE_KEY = "license_key"
    TYPE_GENERIC = "generic"
    TYPE_SUPPORT = "support"
    TYPE_CHOICES = [
        (TYPE_LICENSE_KEY, "License Key"),
        (TYPE_GENERIC, "Generic"),
        (TYPE_SUPPORT, "Support"),
    ]
    email_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default=TYPE_GENERIC,
        db_index=True,
    )  # CHANGED:

    # Provider details (SendGrid message id if you capture it)
    provider = models.CharField(max_length=50, blank=True, default="sendgrid")  # CHANGED:
    provider_message_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:

    # Status
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_QUEUED = "queued"
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_QUEUED, "Queued"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )  # CHANGED:

    error_message = models.TextField(blank=True, default="")  # CHANGED:

    # Minimal context (safe): store masked key details, plan code, site_url, etc.
    meta = models.JSONField(default=dict, blank=True)  # CHANGED:

    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    sent_at = models.DateTimeField(null=True, blank=True)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.email_type} → {self.to_email} ({self.status})"

    # Convenience helpers (optional but nice)
    def mark_sent(self, provider_message_id: str = "") -> None:
        self.status = self.STATUS_SENT  # CHANGED:
        if provider_message_id:
            self.provider_message_id = provider_message_id  # CHANGED:
        self.sent_at = timezone.now()  # CHANGED:
        self.save(update_fields=["status", "provider_message_id", "sent_at"])  # CHANGED:

    def mark_failed(self, error: str) -> None:
        self.status = self.STATUS_FAILED  # CHANGED:
        self.error_message = (error or "")[:5000]  # CHANGED:
        self.save(update_fields=["status", "error_message"])  # CHANGED:
