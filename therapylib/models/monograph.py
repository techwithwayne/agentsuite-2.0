"""
therapylib.models.monograph
Pointer to the current published version for a Substance.
"""
from django.db import models


class Monograph(models.Model):
    substance = models.OneToOneField("therapylib.Substance", on_delete=models.CASCADE, related_name="monograph")
    current_version = models.ForeignKey(
        "therapylib.MonographVersion",
        on_delete=models.PROTECT,
        related_name="as_current_for",
        null=True,
        blank=True,
        help_text="Set after publishing a version."
    )

    class Meta:
        ordering = ("substance__name",)

    def __str__(self) -> str:
        return f"Monograph: {self.substance.name}"
"""therapylib.models.monograph"""

