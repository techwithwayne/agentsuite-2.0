# /home/techwithwayne/agentsuite/postpress_ai/models/license.py
from __future__ import annotations  # CHANGED:

"""
PostPress AI — Licensing Models: License

========= CHANGE LOG =========
2025-12-24 • Create License model as Django source-of-truth for plan + limits + status.  # CHANGED:
           • Add plan/status enums aligned to /tyler pricing rules.                       # CHANGED:
           • Add safe key masking helper (never display/log full license keys).          # CHANGED:
"""

from django.db import models  # CHANGED:
from django.utils import timezone  # CHANGED:


def _mask_key(k: str) -> str:  # CHANGED:
    """
    Safe display helper (admin/UI only). Never log or print full keys.

    Example:
      ABCD…WXYZ
    """  # CHANGED:
    k = (k or "").strip()  # CHANGED:
    if len(k) <= 8:  # CHANGED:
        return "****"  # CHANGED:
    return f"{k[:4]}…{k[-4:]}"  # CHANGED:


class LicenseStatus(models.TextChoices):  # CHANGED:
    ACTIVE = "active", "Active"  # CHANGED:
    CANCELED = "canceled", "Canceled"  # CHANGED:
    EXPIRED = "expired", "Expired"  # CHANGED:
    PAUSED = "paused", "Paused"  # CHANGED:


class LicensePlan(models.TextChoices):  # CHANGED:
    # Matches carryover prompt plan slugs (and /tyler pricing mapping).  # CHANGED:
    SOLO = "solo", "Solo"  # CHANGED:
    CREATOR = "creator", "Creator"  # CHANGED:
    STUDIO = "studio", "Studio"  # CHANGED:
    AGENCY = "agency", "Agency (AI Included)"  # CHANGED:
    AGENCY_BYO = "agency_byo", "Agency Unlimited (BYO Key)"  # CHANGED:


class License(models.Model):  # CHANGED:
    """
    Django-authoritative license record.

    Required fields per spec:
      - plan_slug
      - max_sites (nullable for unlimited)
      - byo_key_required
      - ai_included
      - status (active/canceled/expired/paused)

    Notes:
      - Activations are tracked via related model `Activation` (added in activation.py next).
      - We do NOT store any OpenAI keys here. BYO is enforced by flags + WP-side setting.
    """  # CHANGED:

    key = models.CharField(max_length=128, unique=True)  # CHANGED:

    plan_slug = models.CharField(  # CHANGED:
        max_length=32,  # CHANGED:
        choices=LicensePlan.choices,  # CHANGED:
    )  # CHANGED:

    status = models.CharField(  # CHANGED:
        max_length=16,  # CHANGED:
        choices=LicenseStatus.choices,  # CHANGED:
        default=LicenseStatus.ACTIVE,  # CHANGED:
    )  # CHANGED:

    # Site limits  # CHANGED:
    max_sites = models.PositiveIntegerField(null=True, blank=True)  # CHANGED:
    unlimited_sites = models.BooleanField(default=False)  # CHANGED:

    # Plan flags  # CHANGED:
    byo_key_required = models.BooleanField(default=False)  # CHANGED:
    ai_included = models.BooleanField(default=True)  # CHANGED:

    # Expiration (optional; Stripe/webhooks can set this later)  # CHANGED:
    expires_at = models.DateTimeField(null=True, blank=True)  # CHANGED:

    created_at = models.DateTimeField(auto_now_add=True)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:

    class Meta:  # CHANGED:
        indexes = [  # CHANGED:
            models.Index(fields=["key"]),  # CHANGED:
            models.Index(fields=["status", "plan_slug"]),  # CHANGED:
        ]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        return f"{self.plan_slug} ({_mask_key(self.key)})"  # CHANGED:

    @property
    def is_active(self) -> bool:  # CHANGED:
        """
        True when:
          - status is active
          - and not past expires_at (if set)
        """  # CHANGED:
        if self.status != LicenseStatus.ACTIVE:  # CHANGED:
            return False  # CHANGED:
        if self.expires_at and timezone.now() > self.expires_at:  # CHANGED:
            return False  # CHANGED:
        return True  # CHANGED:

    def allowed_site_count(self) -> int | None:  # CHANGED:
        """
        Returns:
          - None when unlimited
          - integer max_sites otherwise
        """  # CHANGED:
        if self.unlimited_sites:  # CHANGED:
            return None  # CHANGED:
        return self.max_sites  # CHANGED:

    # NOTE: activation counting/helpers will be added after Activation model exists.  # CHANGED:
