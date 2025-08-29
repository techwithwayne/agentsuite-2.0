"""
therapylib.models.protocol
Protocol header/version for a Condition.
"""
from django.db import models
from .base import TimeStampedModel


class Protocol(TimeStampedModel):
    condition = models.ForeignKey("therapylib.Condition", on_delete=models.CASCADE, related_name="protocols")
    version = models.PositiveIntegerField(default=1, db_index=True)
    summary = models.TextField(blank=True, default="")
    published = models.BooleanField(default=False, db_index=True)

    references = models.ManyToManyField("therapylib.Reference", blank=True, related_name="protocols")

    class Meta:
        unique_together = (("condition", "version"),)
        ordering = ("condition__name", "-version")

    def __str__(self) -> str:
        return f"{self.condition.name} v{self.version}"
"""therapylib.models.protocol"""

