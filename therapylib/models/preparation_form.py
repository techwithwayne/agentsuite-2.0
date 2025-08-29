"""
therapylib.models.preparation_form
Capsule, tablet, tincture, powder, tea, topical, etc.
"""
from django.db import models
from .base import NameSlugModel


class PreparationForm(NameSlugModel):
    notes = models.CharField(max_length=255, blank=True, default="")
"""therapylib.models.preparation_form"""

