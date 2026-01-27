# /home/techwithwayne/agentsuite/postpress_ai/models/customer.py

"""
PostPress AI — Customer Command Center models
Path: postpress_ai/models/customer.py

Purpose:
- Create a single "Customer" hub record (email-based identity)
- Track customer sites (for multi-site counting + support visibility)
- Allow internal notes for support/history

Why this file exists:
- You want an admin "command center" to view and manage customer data cleanly.
- This is separate from licensing enforcement logic (which you already consider DONE).

CHANGE LOG
- 2026-01-10: Create Customer, CustomerSite, CustomerNote models.  # CHANGED:
"""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


def _normalize_site_url(site_url: str) -> str:
    """
    Normalize a site URL into a consistent comparison string.

    Examples:
      https://staging9.techwithwayne.com/  -> staging9.techwithwayne.com
      http://example.com/wp/               -> example.com/wp
      example.com                          -> example.com
    """
    if not site_url:
        return ""

    s = site_url.strip()

    # If user entered a bare domain, urlparse treats it as path.
    # Prefix scheme to parse host correctly.
    if "://" not in s:
        s = "https://" + s

    p = urlparse(s)

    host = (p.netloc or "").strip().lower()
    path = (p.path or "").strip()

    # Remove trailing slashes and collapse to a stable form
    path = path.rstrip("/")

    if host and path:
        return f"{host}{path}"
    if host:
        return host
    # fallback if parsing failed
    return site_url.strip().lower().rstrip("/")


class Customer(models.Model):
    """
    A single identity record per paying user.

    Email is the primary key for human identity (unique).
    """

    email = models.EmailField(unique=True)  # CHANGED:
    first_name = models.CharField(max_length=80, blank=True, default="")  # CHANGED:
    last_name = models.CharField(max_length=80, blank=True, default="")  # CHANGED:

    # Optional, but useful if you later want SMS or better support contact.
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                regex=r"^[0-9+\-().\s]*$",
                message="Phone can only contain digits, spaces, and + - ( ) .",
            )
        ],
    )  # CHANGED:

    # Helps you trace where the customer came from (GF/Stripe/manual/etc.)
    source = models.CharField(max_length=50, blank=True, default="")  # CHANGED:

    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:
    last_seen_at = models.DateTimeField(null=True, blank=True)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        name = (f"{self.first_name} {self.last_name}").strip()
        return f"{name} <{self.email}>" if name else self.email

    def touch(self) -> None:
        """Update last_seen_at to now."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])  # CHANGED:


class CustomerSite(models.Model):
    """
    Tracks each distinct site URL the customer uses.

    This is the foundation for:
    - 'sites used' counting
    - site history in admin
    - support triage ("which sites are connected?")
    """

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="sites",
    )  # CHANGED:

    site_url = models.URLField(max_length=500)  # CHANGED:
    site_key = models.CharField(max_length=520, db_index=True)  # CHANGED:

    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    last_seen_at = models.DateTimeField(null=True, blank=True)  # CHANGED:
    is_active = models.BooleanField(default=True)  # CHANGED:

    notes = models.TextField(blank=True, default="")  # CHANGED:

    class Meta:
        ordering = ["-last_seen_at", "-first_seen_at"]  # CHANGED:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "site_key"],
                name="uniq_customer_sitekey",
            )
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.customer.email} → {self.site_url}"

    def save(self, *args, **kwargs):
        # CHANGED: Ensure stable key is always set.
        self.site_key = _normalize_site_url(self.site_url)
        super().save(*args, **kwargs)


class CustomerNote(models.Model):
    """
    Internal-only notes. Great for support: refunds, special handling, etc.
    """

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="notes_log",
    )  # CHANGED:

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="postpress_customer_notes",
    )  # CHANGED:

    note = models.TextField()  # CHANGED:
    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"Note for {self.customer.email} @ {self.created_at:%Y-%m-%d}"
