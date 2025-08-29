"""
therapylib.models.reference
Bibliographic reference for citations.
"""
from django.db import models
from .base import TimeStampedModel


class Reference(TimeStampedModel):
    title = models.CharField(max_length=500)
    authors = models.CharField(max_length=500, blank=True, default="")
    year = models.PositiveIntegerField(null=True, blank=True)
    journal = models.CharField(max_length=255, blank=True, default="")
    doi = models.CharField(max_length=128, blank=True, default="")
    url = models.URLField(blank=True, default="")
    pmid = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["pmid"]),
            models.Index(fields=["doi"]),
            models.Index(fields=["year"]),
        ]

    def __str__(self) -> str:
        core = self.title[:80]
        return f"{core}…" if len(self.title) > 80 else core
"""therapylib.models.reference"""

