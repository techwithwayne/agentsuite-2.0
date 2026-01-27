# /home/techwithwayne/agentsuite/postpress_ai/models/credit.py

"""
PostPress AI — Credits (ledger-based)
Path: postpress_ai/models/credit.py

Purpose:
- Track credits in a clean, auditable way:
  - Monthly plan grants (optional)
  - One-time credit packs (small/medium/large)
  - Usage/spend events (optional)
  - Manual adjustments (support)

Design rules:
- Ledger, not a single "credits_remaining" integer.
- Allows future changes without breaking accounting.
- Does NOT change your current licensing enforcement (DONE per your instruction).

CHANGE LOG
- 2026-01-10: Add CreditLedger + CreditPackPurchase models.  # CHANGED:
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class CreditPackPurchase(models.Model):
    """
    One-time credit pack purchase (small/medium/large) that adds credits.
    """

    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="credit_packs",
    )  # CHANGED:

    # Optional linkage to license/subscription/order if you want it later
    license = models.ForeignKey(
        "postpress_ai.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_packs",
    )  # CHANGED:

    subscription = models.ForeignKey(
        "postpress_ai.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_packs",
    )  # CHANGED:

    PACK_SMALL = "small"
    PACK_MEDIUM = "medium"
    PACK_LARGE = "large"
    PACK_CHOICES = [
        (PACK_SMALL, "Small"),
        (PACK_MEDIUM, "Medium"),
        (PACK_LARGE, "Large"),
    ]
    pack_type = models.CharField(max_length=20, choices=PACK_CHOICES)  # CHANGED:

    credits_granted = models.PositiveIntegerField(default=0)  # CHANGED:

    # Stripe refs (if purchased via Stripe)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")  # CHANGED:

    currency = models.CharField(max_length=10, blank=True, default="usd")  # CHANGED:
    amount_cents = models.PositiveIntegerField(default=0)  # CHANGED:

    meta = models.JSONField(default=dict, blank=True)  # CHANGED:
    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:
        indexes = [
            models.Index(fields=["pack_type", "created_at"]),
            models.Index(fields=["stripe_payment_intent_id"]),
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.customer.email} — pack:{self.pack_type} (+{self.credits_granted})"


class CreditLedger(models.Model):
    """
    Immutable-ish credit ledger entries. Positive adds credits, negative spends credits.
    """

    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="credit_ledger",
    )  # CHANGED:

    # Optional linkage
    license = models.ForeignKey(
        "postpress_ai.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_ledger",
    )  # CHANGED:

    subscription = models.ForeignKey(
        "postpress_ai.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_ledger",
    )  # CHANGED:

    credit_pack = models.ForeignKey(
        "postpress_ai.CreditPackPurchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )  # CHANGED:

    TYPE_MONTHLY_GRANT = "monthly_grant"
    TYPE_PACK_GRANT = "pack_grant"
    TYPE_SPEND = "spend"
    TYPE_MANUAL = "manual_adjust"
    TYPE_CHOICES = [
        (TYPE_MONTHLY_GRANT, "Monthly Grant"),
        (TYPE_PACK_GRANT, "Pack Grant"),
        (TYPE_SPEND, "Spend"),
        (TYPE_MANUAL, "Manual Adjust"),
    ]
    entry_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)  # CHANGED:

    # Positive = add credits, Negative = spend credits
    amount = models.IntegerField()  # CHANGED:

    # Optional "period key" for monthly grants (e.g., 2026-01)
    period_key = models.CharField(max_length=20, blank=True, default="", db_index=True)  # CHANGED:

    description = models.CharField(max_length=255, blank=True, default="")  # CHANGED:
    meta = models.JSONField(default=dict, blank=True)  # CHANGED:

    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:

    class Meta:
        ordering = ["-created_at"]  # CHANGED:
        indexes = [
            models.Index(fields=["entry_type", "created_at"]),
            models.Index(fields=["period_key"]),
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        sign = "+" if self.amount >= 0 else ""
        return f"{self.customer.email} — {self.entry_type} {sign}{self.amount}"

    @staticmethod
    def balance_for_customer(customer_id: int) -> int:
        """
        Current balance = sum of all ledger amounts.
        """
        return (
            CreditLedger.objects.filter(customer_id=customer_id).aggregate(models.Sum("amount"))["amount__sum"]
            or 0
        )  # CHANGED:
