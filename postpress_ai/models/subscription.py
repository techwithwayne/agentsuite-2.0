# /home/techwithwayne/agentsuite/postpress_ai/models/subscription.py

"""
PostPress AI — Subscription model
Path: postpress_ai/models/subscription.py

Purpose:
- Track a customer's current plan/entitlement at the business level.
- Store Stripe identifiers for audit/support (customer id, subscription id, etc.).
- Provide a stable place to answer:
  "What plan is this customer on?" and "Is it active?"

Important:
- This does NOT redesign licensing enforcement.
- Your existing License/Activation logic can remain authoritative.
- This model is the Command Center layer.

CHANGE LOG
- 2026-01-10: Add Subscription model linked to Customer + Plan.  # CHANGED:
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class Subscription(models.Model):
    # Customer + Plan
    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )  # CHANGED:

    plan = models.ForeignKey(
        "postpress_ai.Plan",
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )  # CHANGED:

    # Status
    STATUS_ACTIVE = "active"
    STATUS_CANCELED = "canceled"
    STATUS_PAST_DUE = "past_due"
    STATUS_INCOMPLETE = "incomplete"
    STATUS_TRIALING = "trialing"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_TRIALING, "Trialing"),
        (STATUS_PAST_DUE, "Past Due"),
        (STATUS_INCOMPLETE, "Incomplete"),
        (STATUS_CANCELED, "Canceled"),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )  # CHANGED:

    # Stripe references (optional, but extremely useful)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:

    # Period tracking (optional; helps support and "is it current?")
    current_period_start = models.DateTimeField(null=True, blank=True)  # CHANGED:
    current_period_end = models.DateTimeField(null=True, blank=True)  # CHANGED:
    cancel_at_period_end = models.BooleanField(default=False)  # CHANGED:

    # Admin-only notes/metadata for support
    notes = models.TextField(blank=True, default="")  # CHANGED:
    meta = models.JSONField(default=dict, blank=True)  # CHANGED:

    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["stripe_customer_id"]),
            models.Index(fields=["stripe_subscription_id"]),
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.customer.email} — {self.plan.code} ({self.status})"

    @property
    def is_active(self) -> bool:
        return self.status in {self.STATUS_ACTIVE, self.STATUS_TRIALING}  # CHANGED:

    @property
    def max_sites(self):
        """
        Effective max sites from plan.
        None means unlimited.
        """
        return getattr(self.plan, "max_sites", None)  # CHANGED:

    @property
    def ai_mode(self) -> str:
        return getattr(self.plan, "ai_mode", "included")  # CHANGED:
