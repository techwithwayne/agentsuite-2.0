from __future__ import annotations

from django.db import models
from django.utils import timezone

from .license import License
from .license_site import LicenseSite


class RemoteDraftLog(models.Model):
    """
    Audit trail for remote draft relay attempts.
    """

    license = models.ForeignKey(
        License,
        on_delete=models.CASCADE,
        related_name="remote_draft_logs",
    )

    source_site = models.ForeignKey(
        LicenseSite,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remote_drafts_sent",
    )

    target_site = models.ForeignKey(
        LicenseSite,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="remote_drafts_received",
    )

    source_site_id_raw = models.CharField(max_length=64, blank=True)
    target_site_id_raw = models.CharField(max_length=64, blank=True)

    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    remote_post_id = models.CharField(max_length=64, blank=True)
    remote_edit_link = models.TextField(blank=True)

    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["license", "created_at"]),
            models.Index(fields=["success"]),
        ]

    def __str__(self) -> str:
        status = "ok" if self.success else "error"
        return f"{self.license_id} remote draft [{status}]"
