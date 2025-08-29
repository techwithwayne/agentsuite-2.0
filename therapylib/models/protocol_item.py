"""
therapylib.models.protocol_item
Tiered items inside a Protocol (first-line / adjunct / experimental).
"""
from django.db import models


class ProtocolItem(models.Model):
    TIER_FIRST = "first_line"
    TIER_ADJUNCT = "adjunct"
    TIER_EXPERIMENTAL = "experimental"
    TIER_CHOICES = [
        (TIER_FIRST, "First-line"),
        (TIER_ADJUNCT, "Adjunct"),
        (TIER_EXPERIMENTAL, "Experimental"),
    ]

    protocol = models.ForeignKey("therapylib.Protocol", on_delete=models.CASCADE, related_name="items")
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_FIRST, db_index=True)

    substance = models.ForeignKey("therapylib.Substance", on_delete=models.PROTECT, related_name="protocol_items")
    preparation_form = models.ForeignKey("therapylib.PreparationForm", on_delete=models.SET_NULL, null=True, blank=True)

    dose_text = models.CharField(max_length=128, blank=True, default="", help_text="Human-readable dose")
    duration = models.CharField(max_length=64, blank=True, default="")
    rationale = models.TextField(blank=True, default="")

    evidence = models.ForeignKey("therapylib.EvidenceTag", on_delete=models.SET_NULL, null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("tier", "sort_order", "substance__name")
        indexes = [models.Index(fields=["tier"])]

    def __str__(self) -> str:
        return f"{self.substance.name} ({self.get_tier_display()})"
"""therapylib.models.protocol_item"""

