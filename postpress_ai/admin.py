# /home/techwithwayne/agentsuite/postpress_ai/admin.py
from __future__ import annotations  # CHANGED:

"""
PostPress AI — Django Admin Registrations

========= CHANGE LOG =========
2025-12-24 • Register PostPress AI models in this app's admin.py (isolated + modular).     # CHANGED:
           • Add StoredArticle admin listing (simple, searchable).                          # CHANGED:
           • Add License admin listing with SAFE masked key display (no full key exposure). # CHANGED:
           • Forward-compatible: Activation admin auto-registers when model exists.         # CHANGED:
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
