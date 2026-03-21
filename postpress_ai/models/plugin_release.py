from __future__ import annotations

import os

from django.db import models, transaction


class PluginRelease(models.Model):
    product_slug = models.CharField(max_length=100, default="postpress-ai", db_index=True)
    version = models.CharField(max_length=50, db_index=True)
    zip_file = models.FileField(upload_to="postpress_ai/releases/")
    filename = models.CharField(max_length=255, blank=True, default="")
    changelog = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=False, db_index=True)
    released_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-released_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_slug", "version"],
                name="uniq_plugin_release_slug_version",
            )
        ]
        indexes = [
            models.Index(fields=["product_slug", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_slug} {self.version}"

    def save(self, *args, **kwargs):
        if not self.filename and getattr(self, "zip_file", None):
            try:
                self.filename = os.path.basename(self.zip_file.name or "")
            except Exception:
                self.filename = self.filename or ""

        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_active:
                type(self).objects.filter(
                    product_slug=self.product_slug,
                    is_active=True,
                ).exclude(pk=self.pk).update(is_active=False)
