# /home/techwithwayne/agentsuite/postpress_ai/models/entitlement.py

"""
PostPress AI — Entitlement model (Command Center glue)
Path: postpress_ai/models/entitlement.py

Purpose:
- Provide a single "what does this customer currently have?" record that ties together:
  Customer ↔ Plan ↔ (optional) Subscription ↔ (optional) License
- Keep licensing enforcement as-is (DONE per your instruction).
- Enable admin visibility and clean linking for emails/support.

Design:
- Entitlement can reference a Plan directly.
- Entitlement can optionally link to a License (key) and/or Subscription (Stripe).
- "Unlimited" is represented by max_sites_override = NULL and Plan.max_sites = NULL.

CHANGE LOG
- 2026-01-10: Create Entitlement model to connect Customer/Plan/License/Subscription.  # CHANGED:
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class Entitlement(models.Model):
    # Required hub
    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="entitlements",
    )  # CHANGED:

    plan = models.ForeignKey(
        "postpress_ai.Plan",
        on_delete=models.PROTECT,
        related_name="entitlements",
    )  # CHANGED:

    # Optional links (depends on your existing plumbing)
    # - If you issue licenses from Stripe webhook, you may link both.
    # - If you issue license later, you can link license later.
    subscription = models.ForeignKey(
        "postpress_ai.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entitlements",
    )  # CHANGED:

    license = models.ForeignKey(
        "postpress_ai.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entitlements",
    )  # CHANGED:

    # Status: business view (separate from License.status)
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_CANCELED, "Canceled"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )  # CHANGED:

    # Overrides (rare, but useful for support/manual adjustments)
    # NULL means "use plan default". If plan default is NULL, that's unlimited.
    max_sites_override = models.PositiveIntegerField(null=True, blank=True)  # CHANGED:

    # Notes & metadata for support
    notes = models.TextField(blank=True, default="")  # CHANGED:
    meta = models.JSONField(default=dict, blank=True)  # CHANGED:

    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.customer.email} — {self.plan.code} ({self.status})"

    @property
    def effective_max_sites(self):
        """
        Effective max-sites for this entitlement:
        - If max_sites_override is set -> use it
        - Else -> use plan.max_sites (NULL means unlimited)
        """
        if self.max_sites_override is not None:
            return self.max_sites_override  # CHANGED:
        return getattr(self.plan, "max_sites", None)  # CHANGED:

    @property
    def is_unlimited(self) -> bool:
        return self.effective_max_sites is None  # CHANGED:

    @property
    def effective_ai_mode(self) -> str:
        """
        Mirrors Plan.ai_mode (included/byo_key) for convenience.
        """
        return getattr(self.plan, "ai_mode", "included")  # CHANGED:

    @property
    def is_active(self) -> bool:
        return self.status == self.STATUS_ACTIVE  # CHANGED:
