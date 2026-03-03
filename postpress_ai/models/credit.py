# /home/techwithwayne/agentsuite/postpress_ai/models/credit.py

"""
PostPress AI - Credits (ledger-based)
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
- Does NOT change your current licensing enforcement.

CHANGE LOG
- 2026-01-10: Add CreditLedger + CreditPackPurchase models.
- 2026-03-02: ADD: Idempotency support on CreditLedger (prevents double grants for campaign/trial issuance).
           FIX: Replace mojibake characters for safer logs/UI.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone


class CreditPackPurchase(models.Model):
    """One-time credit pack purchase (small/medium/large) that adds credits."""

    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="credit_packs",
    )

    # Optional linkage to license/subscription/order if you want it later
    license = models.ForeignKey(
        "postpress_ai.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_packs",
    )

    subscription = models.ForeignKey(
        "postpress_ai.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_packs",
    )

    PACK_SMALL = "small"
    PACK_MEDIUM = "medium"
    PACK_LARGE = "large"
    PACK_CHOICES = [
        (PACK_SMALL, "Small"),
        (PACK_MEDIUM, "Medium"),
        (PACK_LARGE, "Large"),
    ]
    pack_type = models.CharField(max_length=20, choices=PACK_CHOICES)

    credits_granted = models.PositiveIntegerField(default=0)

    # Stripe refs (if purchased via Stripe)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, default="")
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")

    currency = models.CharField(max_length=10, blank=True, default="usd")
    amount_cents = models.PositiveIntegerField(default=0)

    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["pack_type", "created_at"]),
            models.Index(fields=["stripe_payment_intent_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.customer.email} - pack:{self.pack_type} (+{self.credits_granted})"


class CreditLedger(models.Model):
    """Immutable-ish credit ledger entries. Positive adds credits, negative spends credits."""

    customer = models.ForeignKey(
        "postpress_ai.Customer",
        on_delete=models.CASCADE,
        related_name="credit_ledger",
    )

    # Optional linkage
    license = models.ForeignKey(
        "postpress_ai.License",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_ledger",
    )

    subscription = models.ForeignKey(
        "postpress_ai.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_ledger",
    )

    credit_pack = models.ForeignKey(
        "postpress_ai.CreditPackPurchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_entries",
    )

    TYPE_MONTHLY_GRANT = "monthly_grant"
    TYPE_PACK_GRANT = "pack_grant"
    TYPE_CAMPAIGN_GRANT = "campaign_grant"
    TYPE_SPEND = "spend"
    TYPE_MANUAL = "manual_adjust"
    TYPE_CHOICES = [
        (TYPE_MONTHLY_GRANT, "Monthly Grant"),
        (TYPE_PACK_GRANT, "Pack Grant"),
        (TYPE_CAMPAIGN_GRANT, "Campaign Grant"),
        (TYPE_SPEND, "Spend"),
        (TYPE_MANUAL, "Manual Adjust"),
    ]
    entry_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)

    # Positive = add credits, Negative = spend credits
    amount = models.IntegerField()

    # Optional "period key" for monthly grants (e.g., 2026-01)
    period_key = models.CharField(max_length=20, blank=True, default="", db_index=True)

    # Idempotency guard:
    # - Set this for grants that MUST NOT be duplicated (ex: trial/campaign issuance).
    # - Unique only when non-empty.
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)

    description = models.CharField(max_length=255, blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entry_type", "created_at"]),
            models.Index(fields=["period_key"]),
            models.Index(fields=["idempotency_key"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_creditledger_idempotency_key",
            ),
        ]

    def __str__(self) -> str:
        sign = "+" if self.amount >= 0 else ""
        return f"{self.customer.email} - {self.entry_type} {sign}{self.amount}"

    @staticmethod
    def balance_for_customer(customer_id: int) -> int:
        """Current balance = sum of all ledger amounts."""
        return (
            CreditLedger.objects.filter(customer_id=customer_id).aggregate(models.Sum("amount"))["amount__sum"]
            or 0
        )

    @classmethod
    def create_idempotent(
        cls,
        *,
        idempotency_key: str,
        customer: Any,
        amount: int,
        entry_type: str,
        license: Any | None = None,
        subscription: Any | None = None,
        credit_pack: Any | None = None,
        period_key: str = "",
        description: str = "",
        meta: dict[str, Any] | None = None,
    ) -> tuple["CreditLedger", bool]:
        """Create a ledger entry once.

        Returns: (entry, created)
          - created=True  -> new entry was created
          - created=False -> existing entry returned (same idempotency_key)

        This is the core primitive we will use for the trial_25k_14d grant.
        """
        key = (idempotency_key or "").strip()
        if not key:
            raise ValueError("idempotency_key is required for create_idempotent")

        meta = meta or {}

        try:
            with transaction.atomic():
                obj = cls.objects.create(
                    idempotency_key=key,
                    customer=customer,
                    license=license,
                    subscription=subscription,
                    credit_pack=credit_pack,
                    entry_type=entry_type,
                    amount=amount,
                    period_key=period_key,
                    description=description,
                    meta=meta,
                )
                return obj, True
        except IntegrityError:
            existing = cls.objects.filter(idempotency_key=key).order_by("-id").first()
            if existing is not None:
                return existing, False
            raise
