from django.contrib import admin
from .models import (
    Category, PreparationForm, EvidenceTag, Reference,
    Substance, Monograph, MonographVersion, DoseRange,
    Condition, Protocol, ProtocolItem,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(PreparationForm)
class PreparationFormAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(EvidenceTag)
class EvidenceTagAdmin(admin.ModelAdmin):
    list_display = ("name", "weight", "is_active")
    search_fields = ("name",)
    ordering = ("-weight", "name")


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("__str__", "year", "journal", "pmid", "doi")
    search_fields = ("title", "authors", "journal", "pmid", "doi")
    list_filter = ("year",)


class DoseRangeInline(admin.TabularInline):
    model = DoseRange
    extra = 1


@admin.register(MonographVersion)
class MonographVersionAdmin(admin.ModelAdmin):
    list_display = ("substance", "version", "created_at", "updated_at")
    list_filter = ("version",)
    search_fields = ("substance__name", "indications", "mechanism")
    inlines = [DoseRangeInline]
    filter_horizontal = ("references",)


@admin.register(Monograph)
class MonographAdmin(admin.ModelAdmin):
    list_display = ("substance", "current_version")
    search_fields = ("substance__name",)


@admin.register(Substance)
class SubstanceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "slug", "summary")
    filter_horizontal = ("forms",)


class ProtocolItemInline(admin.TabularInline):
    model = ProtocolItem
    extra = 1


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name", "slug", "aliases")
    list_filter = ("is_active",)


@admin.register(Protocol)
class ProtocolAdmin(admin.ModelAdmin):
    list_display = ("condition", "version", "published", "created_at")
    list_filter = ("published", "version")
    search_fields = ("condition__name", "summary")
    inlines = [ProtocolItemInline]
    filter_horizontal = ("references",)
