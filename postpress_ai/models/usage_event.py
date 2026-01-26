# -*- coding: utf-8 -*-
"""
PostPress AI — UsageEvent model (token accounting)

Purpose:
- Track AI token usage per license + site + endpoint (generate/preview/translate)
- Enable accurate monthly_used / remaining calculations in license.v1
- Keep schema stable even if provider usage formats vary

========= CHANGE LOG =========
2026-01-26:
- ADD: UsageEvent model for token accounting (license, site_url, view, provider/model, token counts).  # CHANGED:
- HARDEN: Optional activation FK + safe site_url normalization helper.                                 # CHANGED:
- HARDEN: Indexes for fast monthly aggregation + admin queries.                                       # CHANGED:
"""

from __future__ import annotations

from typing import Any, Optional

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .activation import Activation
from .license import License


class UsageEvent(models.Model):
    """
    A single token usage event.

    Notes:
    - Django is the source of truth for usage.
    - WP should never compute usage; it only displays the deterministic snapshots returned by Django.
    - We store token counts as integers with non-negative validators.
    - We keep provider/model/run identifiers optional because different providers expose different shapes.
    """

    # --- Ownership / context ---
    license = models.ForeignKey(  # CHANGED:
        License,
        on_delete=models.CASCADE,
        related_name="usage_events",
        db_index=True,
    )

    # Optional convenience link (not required for correctness).
    activation = models.ForeignKey(  # CHANGED:
        Activation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )

    site_url = models.CharField(  # CHANGED:
        max_length=255,
        db_index=True,
        help_text="Normalized scheme://host[:port] (path/query stripped).",
    )

    # e.g. "generate" | "preview" | "translate"
    view = models.CharField(  # CHANGED:
        max_length=64,
        db_index=True,
        help_text="Which endpoint/view produced this usage event (generate/preview/translate).",
    )

    # --- Provider details ---
    provider = models.CharField(  # CHANGED:
        max_length=64,
        default="openai",
        db_index=True,
        help_text="AI provider identifier (e.g., openai).",
    )

    model = models.CharField(  # CHANGED:
        max_length=128,
        blank=True,
        default="",
        help_text="Model name as reported by the provider (optional).",
    )

    # Provider request/run identifiers (optional; useful for support/debugging)
    request_id = models.CharField(  # CHANGED:
        max_length=128,
        blank=True,
        default="",
        help_text="Provider request id (if available).",
    )
    run_id = models.CharField(  # CHANGED:
        max_length=128,
        blank=True,
        default="",
        help_text="Provider run id (if available).",
    )

    # --- Token accounting ---
    prompt_tokens = models.IntegerField(  # CHANGED:
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Prompt/input tokens used.",
    )
    completion_tokens = models.IntegerField(  # CHANGED:
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Completion/output tokens used.",
    )
    total_tokens = models.IntegerField(  # CHANGED:
        default=0,
        validators=[MinValueValidator(0)],
        db_index=True,
        help_text="Total tokens used (prompt + completion when available).",
    )

    # If you later support non-token costs (images/audio/etc), this lets us extend without breaking shape.
    units = models.CharField(  # CHANGED:
        max_length=32,
        default="tokens",
        help_text="Accounting unit (default: tokens).",
    )

    # --- Outcome / metadata ---
    ok = models.BooleanField(  # CHANGED:
        default=True,
        db_index=True,
        help_text="Whether the AI call completed successfully.",
    )
    error_code = models.CharField(  # CHANGED:
        max_length=64,
        blank=True,
        default="",
        help_text="Short error code for failures (optional).",
    )

    meta = models.JSONField(  # CHANGED:
        default=dict,
        blank=True,
        help_text="Provider-specific safe metadata (no secrets).",
    )

    created_at = models.DateTimeField(  # CHANGED:
        default=timezone.now,
        db_index=True,
        help_text="Event timestamp.",
    )

    class Meta:
        db_table = "ppa_usage_event"  # CHANGED:
        ordering = ["-created_at"]  # CHANGED:
        indexes = [  # CHANGED:
            models.Index(fields=["license", "created_at"], name="ppa_use_lic_dt"),  # CHANGED:
            models.Index(fields=["site_url", "created_at"], name="ppa_use_site_dt"),  # CHANGED:
            models.Index(fields=["view", "created_at"], name="ppa_use_view_dt"),  # CHANGED:
        ]

    def __str__(self) -> str:
        return f"UsageEvent({self.license_id}, {self.view}, {self.total_tokens} {self.units})"

    # ----------------------------
    # Helpers
    # ----------------------------

    @staticmethod
    def normalize_site_url(raw: Any) -> str:  # CHANGED:
        """
        Normalize to the same canonical format used by Activation.normalize_site_url (if available).
        """
        try:
            fn = getattr(Activation, "normalize_site_url", None)
            if callable(fn):
                out = fn(str(raw))
                return (out or "").strip()
        except Exception:
            pass
        return (str(raw) if raw is not None else "").strip()

    @classmethod
    def build(  # CHANGED:
        cls,
        *,
        license: License,
        site_url: str,
        view: str,
        provider: str = "openai",
        model: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: Optional[int] = None,
        ok: bool = True,
        error_code: str = "",
        request_id: str = "",
        run_id: str = "",
        meta: Optional[dict] = None,
        activation: Optional[Activation] = None,
        created_at=None,
    ) -> "UsageEvent":
        """
        Construct a UsageEvent instance safely (does not save).

        We compute total_tokens if not provided to stay deterministic.
        """
        s = cls.normalize_site_url(site_url)  # CHANGED:
        p = int(prompt_tokens or 0)
        c = int(completion_tokens or 0)
        t = int(total_tokens) if total_tokens is not None else int(p + c)  # CHANGED:
        return cls(
            license=license,
            activation=activation,
            site_url=s,
            view=str(view or "").strip()[:64],
            provider=str(provider or "openai").strip()[:64],
            model=str(model or "").strip()[:128],
            prompt_tokens=max(0, p),
            completion_tokens=max(0, c),
            total_tokens=max(0, t),
            ok=bool(ok),
            error_code=str(error_code or "").strip()[:64],
            request_id=str(request_id or "").strip()[:128],
            run_id=str(run_id or "").strip()[:128],
            meta=meta or {},
            created_at=created_at or timezone.now(),
        )
