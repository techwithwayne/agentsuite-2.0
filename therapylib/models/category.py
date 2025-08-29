"""
therapylib.models.category
Top-level taxonomy for substances (Herb, Vitamin, Mineral, Nutraceutical, etc.)
"""
from django.db import models
from .base import NameSlugModel


class Category(NameSlugModel):
    """
    Example values: Herb, Vitamin, Mineral, Amino Acid, Nutraceutical, Lifestyle
    """
    description = models.TextField(blank=True, default="")

    class Meta(NameSlugModel.Meta):
        verbose_name_plural = "Categories"
"""therapylib.models.category"""

