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
            "max_sites",  # CHANGED:
            "unlimited_sites",  # CHANGED:
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
        if CustomerNote is not None:  # CHANGED:
            inlines.append(CustomerNoteInline)  # CHANGED:
