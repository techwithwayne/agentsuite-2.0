# /home/techwithwayne/agentsuite/postpress_ai/models/activation.py
from __future__ import annotations  # CHANGED:

"""
PostPress AI — Licensing Models: Activation

========= CHANGE LOG =========
2025-12-24 • Create Activation model to track per-site license usage.                 # CHANGED:
           • Normalize site_url to prevent duplicate slot consumption.                # CHANGED:
           • Enforce unique (license, site_url) at the database level.                # CHANGED:
"""

from urllib.parse import urlparse  # CHANGED:

from django.db import models  # CHANGED:
from django.utils import timezone  # CHANGED:

from .license import License  # CHANGED:


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def _normalize_site_url(raw: str) -> str:  # CHANGED:
    """
    Canonicalize a site URL so variants don’t count as multiple activations.

    Rules:
      - Trim whitespace
      - Lowercase host
      - Add scheme if missing (default https)
      - Strip path/query/fragment
      - Strip trailing slash
    """  # CHANGED:
    raw = (raw or "").strip()  # CHANGED:
    if not raw:  # CHANGED:
        return ""  # CHANGED:

    if "://" not in raw:  # CHANGED:
        raw = "https://" + raw  # CHANGED:

    parsed = urlparse(raw)  # CHANGED:
    scheme = (parsed.scheme or "https").lower()  # CHANGED:
    netloc = (parsed.netloc or "").strip().lower()  # CHANGED:

    if not netloc and parsed.path:  # CHANGED:
        netloc = parsed.path.strip().lower()  # CHANGED:

    netloc = netloc.rstrip(".")  # CHANGED:
    return f"{scheme}://{netloc}".rstrip("/")  # CHANGED:


# --------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------


class Activation(models.Model):  # CHANGED:
    """
    One activation per site per license.

    Notes:
      - Django is authoritative; WP only submits site_url.
      - site_fingerprint is optional (future hardening).
      - last_verified_at updated by /license/verify endpoint later.
    """  # CHANGED:

    license = models.ForeignKey(  # CHANGED:
        License,  # CHANGED:
        on_delete=models.CASCADE,  # CHANGED:
        related_name="activations",  # CHANGED:
    )  # CHANGED:

    site_url = models.URLField(max_length=255)  # CHANGED:
    site_fingerprint = models.CharField(max_length=128, null=True, blank=True)  # CHANGED:

    activated_at = models.DateTimeField(auto_now_add=True)  # CHANGED:
    last_verified_at = models.DateTimeField(null=True, blank=True)  # CHANGED:

    class Meta:  # CHANGED:
        constraints = [  # CHANGED:
            models.UniqueConstraint(  # CHANGED:
                fields=["license", "site_url"],  # CHANGED:
                name="unique_activation_per_license_site",  # CHANGED:
            )  # CHANGED:
        ]  # CHANGED:
        indexes = [  # CHANGED:
            models.Index(fields=["site_url"]),  # CHANGED:
            models.Index(fields=["last_verified_at"]),  # CHANGED:
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.site_url} ← {self.license_id}"  # CHANGED:

    def save(self, *args, **kwargs):  # CHANGED:
        # Normalize before save to enforce uniqueness deterministically.  # CHANGED:
        self.site_url = _normalize_site_url(self.site_url)  # CHANGED:
        super().save(*args, **kwargs)  # CHANGED:

    def touch_verified(self):  # CHANGED:
        """Update verification timestamp without altering other fields."""  # CHANGED:
        self.last_verified_at = timezone.now()  # CHANGED:
        self.save(update_fields=["last_verified_at"])  # CHANGED:
