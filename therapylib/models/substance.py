"""
therapylib.models.substance

CHANGE LOG
----------
2025-08-24
- REMOVE: Postgres-only import (ArrayField) that required psycopg.         # CHANGED:
- KEEP: Use JSONField for synonyms so it works on SQLite and Postgres.     # CHANGED:
"""
from django.db import models
from .base import NameSlugModel


class Substance(NameSlugModel):
    """
    Core entity a monograph describes (e.g., Berberine, Magnesium Glycinate).
    SQLite-safe: uses JSONField for synonyms; ManyToMany for forms.
    """
    category = models.ForeignKey(
        "therapylib.Category",
        on_delete=models.PROTECT,
        related_name="substances",
    )
    synonyms = models.JSONField(
        default=list,
        blank=True,
        help_text="List of alternative names"
    )
    summary = models.TextField(blank=True, default="")
    forms = models.ManyToManyField(
        "therapylib.PreparationForm",
        blank=True,
        related_name="substances",
    )

    class Meta(NameSlugModel.Meta):
        indexes = [models.Index(fields=["slug"])]

    def __str__(self) -> str:
        return self.name
