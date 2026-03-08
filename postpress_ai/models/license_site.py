from __future__ import annotations

from django.db import models
from django.utils import timezone

from .license import License


class LicenseSiteStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    BLOCKED = "blocked", "Blocked"


class LicenseSite(models.Model):
    """
    Connected WordPress site for a given PostPress AI license.

    One row = one remote-capable site under one license.
    """

    license = models.ForeignKey(
        License,
        on_delete=models.CASCADE,
        related_name="connected_sites",
    )

    name = models.CharField(max_length=255, blank=True)
    site_url = models.URLField()
    site_token = models.CharField(max_length=128)

    status = models.CharField(
        max_length=16,
        choices=LicenseSiteStatus.choices,
        default=LicenseSiteStatus.PENDING,
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["license", "status"]),
            models.Index(fields=["site_url"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["license", "site_url"],
                name="unique_license_site_url",
            ),
        ]
        ordering = ["site_url"]

    def __str__(self) -> str:
        return f"{self.license_id}:{self.site_url} ({self.status})"
