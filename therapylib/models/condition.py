"""
therapylib.models.condition
Clinical condition/diagnosis (e.g., IBS, PCOS, Anxiety).
"""
from django.db import models
from .base import NameSlugModel


class Condition(NameSlugModel):
    description = models.TextField(blank=True, default="")
    aliases = models.JSONField(default=list, blank=True)

    class Meta(NameSlugModel.Meta):
        indexes = [models.Index(fields=["slug"])]
"""therapylib.models.condition"""

