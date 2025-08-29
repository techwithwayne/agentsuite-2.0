"""
therapylib.models.dose_range
Dosing per preparation form for a given MonographVersion.
"""
from django.db import models
from .base import TimeStampedModel


class DoseRange(TimeStampedModel):
    monograph_version = models.ForeignKey("therapylib.MonographVersion", on_delete=models.CASCADE, related_name="doses")
    form = models.ForeignKey("therapylib.PreparationForm", on_delete=models.PROTECT, related_name="doses")

    amount_min = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    amount_max = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=32, help_text="e.g., mg, g, mL")
    frequency = models.CharField(max_length=64, blank=True, default="", help_text="e.g., 2x/day")
    duration = models.CharField(max_length=64, blank=True, default="", help_text="e.g., 8 weeks")
    notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        unique_together = (("monograph_version", "form", "unit"),)
        indexes = [models.Index(fields=["unit"])]
        ordering = ("form__name", "unit")
"""therapylib.models.dose_range"""

