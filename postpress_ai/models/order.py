"""
postpress_ai.models.order

Stripe fulfillment persistence model (Django authoritative).

We store Stripe identifiers + purchaser info + raw session payload snapshot so:
- Webhook processing is idempotent
- Fulfillment can be audited/replayed safely
- License issuance can be tied to a durable Order record

========= CHANGE LOG =========
2025-12-26 • ADD: Order model for Stripe Checkout fulfillment persistence.  # CHANGED:
"""

from __future__ import annotations

from django.db import models


class Order(models.Model):
    """
    Represents a single Stripe Checkout purchase (centered on checkout.session).
    """

    # ---- Stripe identifiers (idempotency + joins) ----
    stripe_event_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Stripe webhook event id that created/updated this order (if applicable).",
    )

    stripe_session_id = models.CharField(  # CHANGED:
        max_length=255,
        unique=True,  # CHANGED:
        db_index=True,
        help_text="Stripe Checkout Session id (cs_...).",
    )

    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Stripe Customer id (cus_...) if present.",
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="Stripe PaymentIntent id (pi_...) if present.",
    )

    # ---- purchaser ----
    purchaser_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Name captured by Stripe Checkout (if provided).",
    )

    purchaser_email = models.EmailField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Email captured by Stripe Checkout (if provided).",
    )

    # ---- amounts ----
    amount_total = models.IntegerField(
        blank=True,
        null=True,
        help_text="Total amount in the smallest currency unit (e.g., cents).",
    )

    currency = models.CharField(
        max_length=12,
        blank=True,
        null=True,
        help_text="Currency (e.g., 'usd').",
    )

    # ---- status ----
    status = models.CharField(
        max_length=64,
        default="created",
        db_index=True,
        help_text="Order lifecycle status (e.g., created, paid, fulfilled, failed).",
    )

    # ---- raw payload snapshot (for audit/debug) ----
    raw_session = models.JSONField(
        blank=True,
        null=True,
        help_text="Snapshot of the Stripe Checkout Session payload at time of processing.",
    )

    raw_event = models.JSONField(
        blank=True,
        null=True,
        help_text="Snapshot of the Stripe webhook event payload at time of processing.",
    )

    # ---- metadata ----
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Internal notes for debugging/audit (never shown to users).",
    )

    created_at = models.DateTimeField(auto_now_add=True)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["stripe_session_id"]),
            models.Index(fields=["stripe_customer_id"]),
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["purchaser_email"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        email = self.purchaser_email or "unknown-email"
        return f"Order({self.stripe_session_id})<{email}>"
