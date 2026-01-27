# /home/techwithwayne/agentsuite/postpress_ai/admin.py
from __future__ import annotations  # CHANGED:

"""
PostPress AI — Django Admin Registrations

========= CHANGE LOG =========
2025-12-24 • Register PostPress AI models in this app's admin.py (isolated + modular).     # CHANGED:
           • Add StoredArticle admin listing (simple, searchable).                          # CHANGED:
           • Add License admin listing with SAFE masked key display (no full key exposure). # CHANGED:
           • Forward-compatible: Activation admin auto-registers when model exists.         # CHANGED:
2026-01-10 • Register Customer Command Center models + Plan model so they show in admin.   # CHANGED:
2026-01-10 • Add EmailLog admin + inline under Customer for license-email visibility.      # CHANGED:
2026-01-26 • ADMIN UX: Show Effective Max/Unlimited + Tokens in License list (computed from PLAN_DEFAULTS). # CHANGED:
"""

from django.contrib import admin  # CHANGED:


# Import models directly (avoid relying on package __init__ exports).  # CHANGED:
try:  # CHANGED:
    from .models.article import StoredArticle  # CHANGED:
except Exception:  # CHANGED:
    StoredArticle = None  # type: ignore  # CHANGED:

try:  # CHANGED:
    from .models.license import License  # CHANGED:
except Exception:  # CHANGED:
    License = None  # type: ignore  # CHANGED:

try:  # CHANGED:
    from .models.activation import Activation  # CHANGED:
except Exception:  # CHANGED:
    Activation = None  # type: ignore  # CHANGED:

# CHANGED: New models (Command Center + Plans)
try:  # CHANGED:
    from .models.customer import Customer, CustomerSite, CustomerNote  # CHANGED:
except Exception:  # CHANGED:
    Customer = None  # type: ignore  # CHANGED:
    CustomerSite = None  # type: ignore  # CHANGED:
    CustomerNote = None  # type: ignore  # CHANGED:

try:  # CHANGED:
    from .models.plan import Plan  # CHANGED:
except Exception:  # CHANGED:
    Plan = None  # type: ignore  # CHANGED:

# CHANGED: Email log model
try:  # CHANGED:
    from .models.email_log import EmailLog  # CHANGED:
except Exception:  # CHANGED:
    EmailLog = None  # type: ignore  # CHANGED:


# --------------------------------------------------------------------------------------
# StoredArticle
# --------------------------------------------------------------------------------------


if StoredArticle is not None:  # CHANGED:

    @admin.register(StoredArticle)  # CHANGED:
    class StoredArticleAdmin(admin.ModelAdmin):  # CHANGED:
        list_display = ("id", "wp_post_id", "title", "source", "stored_at")  # CHANGED:
        search_fields = ("title", "wp_permalink", "subject")  # CHANGED:
        list_filter = ("source",)  # CHANGED:
        ordering = ("-stored_at",)  # CHANGED:


# --------------------------------------------------------------------------------------
# License
# --------------------------------------------------------------------------------------


if License is not None:  # CHANGED:

    @admin.register(License)  # CHANGED:
    class LicenseAdmin(admin.ModelAdmin):  # CHANGED:
        # __str__ already masks the key; list_display uses a safe method too.  # CHANGED:
        list_display = (  # CHANGED:
            "id",  # CHANGED:
            "masked_key",  # CHANGED:
            "plan_slug",  # CHANGED:
            "status",  # CHANGED:

            # Raw DB overrides (often blank by design).  # CHANGED:
            "max_sites",  # CHANGED:
            "unlimited_sites",  # CHANGED:

            # Effective computed entitlements (PLAN_DEFAULTS fallback).  # CHANGED:
            "eff_max_sites",  # CHANGED:
            "eff_unlimited_sites",  # CHANGED:
            "eff_tokens_mode",  # CHANGED:
            "eff_tokens_monthly_limit",  # CHANGED:
            "eff_entitlements_source",  # CHANGED:

            "byo_key_required",  # CHANGED:
            "ai_included",  # CHANGED:
            "expires_at",  # CHANGED:
            "updated_at",  # CHANGED:
        )  # CHANGED:
        search_fields = ("key",)  # CHANGED:
        list_filter = ("plan_slug", "status", "byo_key_required", "ai_included", "unlimited_sites")  # CHANGED:
        ordering = ("-updated_at",)  # CHANGED:

        @admin.display(description="Key")  # CHANGED:
        def masked_key(self, obj):  # CHANGED:
            # Show only a safe masked version in admin lists.  # CHANGED:
            k = (getattr(obj, "key", "") or "").strip()  # CHANGED:
            if len(k) <= 8:  # CHANGED:
                return "****"  # CHANGED:
            return f"{k[:4]}…{k[-4:]}"  # CHANGED:

        # ---- Effective entitlement helpers (read-only; display only; no behavior changes) ----  # CHANGED:
        def _effective_entitlements_safe(self, obj):  # CHANGED:
            """
            Returns entitlements derived from PLAN_DEFAULTS (or overrides) via licensing view helper.

            IMPORTANT: Import is inside the method to avoid circular import risk during admin load.  # CHANGED:
            """
            try:  # CHANGED:
                from postpress_ai.views.license import _effective_entitlements  # CHANGED:
            except Exception:  # CHANGED:
                return {}  # CHANGED:

            try:  # CHANGED:
                ent = _effective_entitlements(obj) or {}  # CHANGED:
            except Exception:  # CHANGED:
                ent = {}  # CHANGED:
            return ent  # CHANGED:

        def _effective_sites_tuple(self, obj):  # CHANGED:
            ent = self._effective_entitlements_safe(obj)  # CHANGED:
            sites = ent.get("sites") if isinstance(ent.get("sites"), dict) else {}  # CHANGED:

            max_sites = sites.get("max")  # CHANGED:
            if max_sites is None:  # CHANGED:
                max_sites = ent.get("max_sites")  # CHANGED:

            unlimited = sites.get("unlimited")  # CHANGED:
            if unlimited is None:  # CHANGED:
                unlimited = ent.get("unlimited_sites")  # CHANGED:

            return (max_sites, bool(unlimited), ent)  # CHANGED:

        @admin.display(description="Eff Max Sites")  # CHANGED:
        def eff_max_sites(self, obj):  # CHANGED:
            max_sites, _unlimited, _ent = self._effective_sites_tuple(obj)  # CHANGED:
            if max_sites is None:  # CHANGED:
                return "-"  # CHANGED:
            try:  # CHANGED:
                return int(max_sites)  # CHANGED:
            except Exception:  # CHANGED:
                return str(max_sites)  # CHANGED:

        @admin.display(description="Eff Unlimited", boolean=True)  # CHANGED:
        def eff_unlimited_sites(self, obj):  # CHANGED:
            _max_sites, unlimited, _ent = self._effective_sites_tuple(obj)  # CHANGED:
            return bool(unlimited)  # CHANGED:

        @admin.display(description="Eff Tokens Mode")  # CHANGED:
        def eff_tokens_mode(self, obj):  # CHANGED:
            ent = self._effective_entitlements_safe(obj)  # CHANGED:
            tokens = ent.get("tokens") if isinstance(ent.get("tokens"), dict) else {}  # CHANGED:
            mode = tokens.get("mode")  # CHANGED:
            return mode or "-"  # CHANGED:

        @admin.display(description="Eff Monthly Tokens")  # CHANGED:
        def eff_tokens_monthly_limit(self, obj):  # CHANGED:
            ent = self._effective_entitlements_safe(obj)  # CHANGED:
            tokens = ent.get("tokens") if isinstance(ent.get("tokens"), dict) else {}  # CHANGED:
            monthly = tokens.get("monthly_limit")  # CHANGED:
            if monthly is None:  # CHANGED:
                return "-"  # CHANGED:
            try:  # CHANGED:
                return f"{int(monthly):,}"  # CHANGED:
            except Exception:  # CHANGED:
                return str(monthly)  # CHANGED:

        @admin.display(description="Ent Src")  # CHANGED:
        def eff_entitlements_source(self, obj):  # CHANGED:
            """
            Simple, admin-only hint:
            - If raw override fields are set, show override.
            - Otherwise, it's plan_defaults (your intended standard).  # CHANGED:
            """
            raw_max = getattr(obj, "max_sites", None)  # CHANGED:
            raw_unl = bool(getattr(obj, "unlimited_sites", False))  # CHANGED:
            if raw_unl or (raw_max is not None and str(raw_max).strip() != ""):  # CHANGED:
                return "license_override"  # CHANGED:
            return "plan_defaults"  # CHANGED:


# --------------------------------------------------------------------------------------
# Activation (forward-compatible; will show after activation.py is implemented + migrated)
# --------------------------------------------------------------------------------------


if Activation is not None:  # CHANGED:

    @admin.register(Activation)  # CHANGED:
    class ActivationAdmin(admin.ModelAdmin):  # CHANGED:
        list_display = ("id", "license_id", "site_url", "activated_at", "last_verified_at")  # CHANGED:
        search_fields = ("site_url", "site_fingerprint", "license__key")  # CHANGED:
        ordering = ("-activated_at",)  # CHANGED:


# --------------------------------------------------------------------------------------
# Plan (shows your /tyler plan definitions)
# --------------------------------------------------------------------------------------


if Plan is not None:  # CHANGED:

    @admin.register(Plan)  # CHANGED:
    class PlanAdmin(admin.ModelAdmin):  # CHANGED:
        list_display = ("code", "name", "max_sites", "ai_mode", "is_active", "updated_at")  # CHANGED:
        list_filter = ("ai_mode", "is_active")  # CHANGED:
        search_fields = ("code", "name")  # CHANGED:
        ordering = ("name",)  # CHANGED:


# --------------------------------------------------------------------------------------
# EmailLog (shows sent/failed license emails)
# --------------------------------------------------------------------------------------


if EmailLog is not None:  # CHANGED:

    @admin.register(EmailLog)  # CHANGED:
    class EmailLogAdmin(admin.ModelAdmin):  # CHANGED:
        list_display = ("id", "email_type", "to_email", "subject", "status", "created_at", "sent_at")  # CHANGED:
        list_filter = ("email_type", "status", "provider")  # CHANGED:
        search_fields = ("to_email", "subject", "provider_message_id")  # CHANGED:
        ordering = ("-created_at",)  # CHANGED:
        readonly_fields = ("created_at", "sent_at")  # CHANGED:


# --------------------------------------------------------------------------------------
# Customer Command Center
# --------------------------------------------------------------------------------------


# CHANGED: Inlines for a clean "command center" view.
if CustomerSite is not None:  # CHANGED:

    class CustomerSiteInline(admin.TabularInline):  # CHANGED:
        model = CustomerSite  # CHANGED:
        extra = 0  # CHANGED:
        fields = ("site_url", "site_key", "is_active", "first_seen_at", "last_seen_at")  # CHANGED:
        readonly_fields = ("site_key", "first_seen_at", "last_seen_at")  # CHANGED:
        show_change_link = True  # CHANGED:


if CustomerNote is not None:  # CHANGED:

    class CustomerNoteInline(admin.TabularInline):  # CHANGED:
        model = CustomerNote  # CHANGED:
        extra = 0  # CHANGED:
        fields = ("note", "created_by", "created_at")  # CHANGED:
        readonly_fields = ("created_at",)  # CHANGED:
        show_change_link = True  # CHANGED:


# CHANGED: Inline EmailLog under Customer so you can see "Welcome..." delivery history.
if EmailLog is not None:  # CHANGED:

    class EmailLogInline(admin.TabularInline):  # CHANGED:
        model = EmailLog  # CHANGED:
        extra = 0  # CHANGED:
        fields = ("email_type", "to_email", "subject", "status", "created_at", "sent_at")  # CHANGED:
        readonly_fields = ("to_email", "subject", "created_at", "sent_at")  # CHANGED:
        show_change_link = True  # CHANGED:
        can_delete = False  # CHANGED:


if Customer is not None:  # CHANGED:

    @admin.register(Customer)  # CHANGED:
    class CustomerAdmin(admin.ModelAdmin):  # CHANGED:
        list_display = ("email", "first_name", "last_name", "source", "created_at", "last_seen_at")  # CHANGED:
        search_fields = ("email", "first_name", "last_name")  # CHANGED:
        list_filter = ("source",)  # CHANGED:
        ordering = ("-created_at",)  # CHANGED:

        inlines = []  # CHANGED:
        if CustomerSite is not None:  # CHANGED:
            inlines.append(CustomerSiteInline)  # CHANGED:
        if EmailLog is not None:  # CHANGED:
            inlines.append(EmailLogInline)  # CHANGED:
        if CustomerNote is not None:  # CHANGED:
            inlines.append(CustomerNoteInline)  # CHANGED:
