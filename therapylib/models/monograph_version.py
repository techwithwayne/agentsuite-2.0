"""
therapylib.models.monograph_version
Versioned clinical content for a Substance.
"""
from django.db import models
from .base import TimeStampedModel


class MonographVersion(TimeStampedModel):
    substance = models.ForeignKey("therapylib.Substance", on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField(default=1, db_index=True)

    # Core sections (free text; we’ll structure further later)
    indications = models.TextField(blank=True, default="")
    mechanism = models.TextField(blank=True, default="")
    dosing_overview = models.TextField(blank=True, default="")
    contraindications = models.TextField(blank=True, default="")
    interactions = models.TextField(blank=True, default="")
    adverse_effects = models.TextField(blank=True, default="")
    pregnancy_lactation = models.TextField(blank=True, default="")
    pediatrics = models.TextField(blank=True, default="")
    geriatrics = models.TextField(blank=True, default="")
    lab_markers = models.TextField(blank=True, default="")
    evidence_summary = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    references = models.ManyToManyField("therapylib.Reference", blank=True, related_name="monograph_versions")

    class Meta:
        unique_together = (("substance", "version"),)
        ordering = ("substance__name", "-version")

    def __str__(self) -> str:
        return f"{self.substance.name} v{self.version}"
"""therapylib.models.monograph_version"""

