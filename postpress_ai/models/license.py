# /home/techwithwayne/agentsuite/postpress_ai/models/license.py
from __future__ import annotations

"""
PostPress AI - Licensing Models: License

========= CHANGE LOG =========
2025-12-24 • Create License model as Django source-of-truth for plan + limits + status.
           • Add plan/status enums aligned to pricing rules.
           • Add safe key masking helper (never display/log full license keys).
2026-03-02 • FIX: Repair file corruption/duplication (multiple __str__/is_active blocks, stray brackets).
           • ADD: trial_25k_14d as a valid plan_slug choice for campaign issuance.
"""

from django.db import models
from django.utils import timezone


def _mask_key(k: str) -> str:
    """
    Safe display helper (admin/UI only). Never log or print full keys.

    Example:
      ABCD...WXYZ
    """
    k = (k or "").strip()
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"


class LicenseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELED = "canceled", "Canceled"
    EXPIRED = "expired", "Expired"
    PAUSED = "paused", "Paused"


class LicensePlan(models.TextChoices):
    """
    IMPORTANT:
    - These choices must include any plan_slug you intend to save into License.plan_slug.
    - Adding choices does NOT require a DB migration (choices are app-level), but it DOES
      prevent validation/admin/UI issues.
    """

    # Paid plans
    SOLO = "solo", "Solo"
    CREATOR = "creator", "Creator"
    STUDIO = "studio", "Studio"
    AGENCY = "agency", "Agency (AI Included)"
    AGENCY_BYO = "agency_byo", "Agency Unlimited (BYO Key)"

    # Campaign / trial plan
    TRIAL_25K_14D = "trial_25k_14d", "Trial 25,000 Tokens (14 Days)"


class License(models.Model):
    """
    Django-authoritative license record.

    Required fields per spec:
      - plan_slug
      - max_sites (nullable for unlimited)
      - byo_key_required
      - ai_included
      - status (active/canceled/expired/paused)

    Notes:
      - Activations are tracked via related model `Activation`.
      - We do NOT store any OpenAI keys here. BYO is enforced by flags + WP-side setting.
    """

    key = models.CharField(max_length=128, unique=True)

    plan_slug = models.CharField(
        max_length=32,
        choices=LicensePlan.choices,
    )

    status = models.CharField(
        max_length=16,
        choices=LicenseStatus.choices,
        default=LicenseStatus.ACTIVE,
    )

    # Site limits
    max_sites = models.PositiveIntegerField(null=True, blank=True)
    unlimited_sites = models.BooleanField(default=False)

    # Plan flags
    byo_key_required = models.BooleanField(default=False)
    ai_included = models.BooleanField(default=True)

    # Expiration (optional; Stripe/webhooks/campaign issuance can set this)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["key"]),
            models.Index(fields=["status", "plan_slug"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.plan_slug} ({_mask_key(self.key)})"

    @property
    def is_expired(self) -> bool:
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    @property
    def is_active(self) -> bool:
        """
        True when:
          - status is active
          - and not past expires_at (if set)
        """
        if self.status != LicenseStatus.ACTIVE:
            return False
        if self.is_expired:
            return False
        return True

    def allowed_site_count(self) -> int | None:
        """
        Returns:
          - None when unlimited
          - integer max_sites otherwise
        """
        if self.unlimited_sites:
            return None
        return self.max_sites

    def mark_expired(self, save: bool = True) -> None:
        """
        Optional convenience method; doesn't run automatically.
        Useful in verify endpoints if you want to flip status when time passes.
        """
        self.status = LicenseStatus.EXPIRED
        if save:
            self.save(update_fields=["status", "updated_at"])