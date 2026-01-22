# /home/techwithwayne/agentsuite/postpress_ai/models/plan.py

"""
PostPress AI — Plan model
Path: postpress_ai/models/plan.py

Purpose:
- Represent plans shown on /tyler (Solo, Creator, Studio, Agency, Agency Unlimited BYO).
- Handle site limits including unlimited (NULL).
- Store AI mode (AI included vs BYO key).
- Optional: store included monthly credits (future-proof).

CHANGE LOG
- 2026-01-10: Add Plan model + helpers + seed defaults.  # CHANGED:
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class Plan(models.Model):
    """
    Plan definition.

    Key design rule:
    - Use max_sites = NULL for unlimited.
    """

    # Stable internal code; use in logic and admin filters.
    code = models.SlugField(unique=True)  # CHANGED:

    # Human-facing name for admin display.
    name = models.CharField(max_length=120)  # CHANGED:

    # NULL means unlimited sites.
    max_sites = models.PositiveIntegerField(null=True, blank=True)  # CHANGED:

    # AI mode for the plan: "included" means PostPress AI provides AI access,
    # "byo_key" means customer must provide their own OpenAI key.
    AI_INCLUDED = "included"
    AI_BYO_KEY = "byo_key"
    AI_MODE_CHOICES = [
        (AI_INCLUDED, "AI Included"),
        (AI_BYO_KEY, "Bring Your Own Key"),
    ]
    ai_mode = models.CharField(
        max_length=20,
        choices=AI_MODE_CHOICES,
        default=AI_INCLUDED,
    )  # CHANGED:

    # Optional: monthly credits included with the plan (if/when you enforce usage).
    credits_monthly_included = models.PositiveIntegerField(default=0)  # CHANGED:

    # Optional: support/perks flags
    priority_support = models.BooleanField(default=False)  # CHANGED:

    is_active = models.BooleanField(default=True)  # CHANGED:
    created_at = models.DateTimeField(default=timezone.now, editable=False)  # CHANGED:
    updated_at = models.DateTimeField(auto_now=True)  # CHANGED:

    class Meta:
        ordering = ["name"]  # CHANGED:

    def __str__(self) -> str:  # CHANGED:
        limit = "Unlimited" if self.max_sites is None else str(self.max_sites)
        ai = "AI Included" if self.ai_mode == self.AI_INCLUDED else "BYO Key"
        return f"{self.name} ({limit} sites, {ai})"

    @property
    def is_unlimited(self) -> bool:
        return self.max_sites is None  # CHANGED:

    def allows_site_count(self, used_sites: int) -> bool:
        """
        Return True if this plan allows another activation given used_sites.
        used_sites should be the count of distinct sites already activated.
        """
        if self.max_sites is None:
            return True
        return used_sites < self.max_sites  # CHANGED:


def seed_default_plans() -> None:
    """
    Idempotent seed for default plans from /tyler.

    Run manually in Django shell after migrate, or wire into a management command later.
    """
    defaults = [
        # code, name, max_sites, ai_mode, monthly_credits, priority_support
        ("solo", "Solo", 1, Plan.AI_INCLUDED, 0, False),
        ("creator", "Creator", 3, Plan.AI_INCLUDED, 0, False),
        ("studio", "Studio", 10, Plan.AI_INCLUDED, 0, False),
        ("agency", "Agency (AI Included)", 25, Plan.AI_INCLUDED, 0, True),
        ("agency_unlimited_byo", "Agency Unlimited (BYO Key)", None, Plan.AI_BYO_KEY, 0, True),
    ]

    for code, name, max_sites, ai_mode, credits, priority in defaults:
        Plan.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "max_sites": max_sites,
                "ai_mode": ai_mode,
                "credits_monthly_included": credits,
                "priority_support": priority,
                "is_active": True,
            },
        )  # CHANGED:
