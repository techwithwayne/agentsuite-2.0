"""
therapylib.models.evidence_tag
Evidence grading labels (e.g., A/B/C or Strong/Moderate/Limited).
"""
from django.db import models
from .base import NameSlugModel


class EvidenceTag(NameSlugModel):
    """
    name examples: A, B, C (or Strong, Moderate, Limited)
    """
    weight = models.PositiveSmallIntegerField(default=0, help_text="Higher = stronger evidence")

    class Meta(NameSlugModel.Meta):
        ordering = ("-weight", "name")
"""therapylib.models.evidence_tag"""

