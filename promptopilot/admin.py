from django.contrib import admin
from .models import AdPrompt, AdResult, PromptHistory
import csv
from django.http import HttpResponse


# 🔁 INLINE RESULT VIEW
class AdResultInline(admin.StackedInline):
    model = AdResult
    can_delete = False
    readonly_fields = ("output_text", "model_used", "created_at")
    extra = 0


# 📤 EXPORT CSV ACTION
def export_as_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{modeladmin.model.__name__}.csv"'
    writer = csv.writer(response)

    fields = [field.name for field in modeladmin.model._meta.fields]
    writer.writerow(fields)

    for obj in queryset:
        writer.writerow([getattr(obj, field) for field in fields])

    return response

export_as_csv.short_description = "Export selected as CSV"


# 🧹 BULK SOFT DELETE / RESTORE
def soft_delete(modeladmin, request, queryset):
    queryset.update(is_active=False)

def restore_active(modeladmin, request, queryset):
    queryset.update(is_active=True)

soft_delete.short_description = "Deactivate selected"
restore_active.short_description = "Reactivate selected"


@admin.register(AdPrompt)
class AdPromptAdmin(admin.ModelAdmin):
    list_display = ("user", "tool", "is_active", "created_at")
    list_filter = ("tool", "is_active", "created_at")
    search_fields = ("user__username", "prompt_text")
    readonly_fields = ("created_at",)
    inlines = [AdResultInline]
    actions = [export_as_csv, soft_delete, restore_active]


@admin.register(AdResult)
class AdResultAdmin(admin.ModelAdmin):
    list_display = ("prompt", "model_used", "created_at")
    list_filter = ("model_used", "created_at")
    search_fields = ("output_text",)
    readonly_fields = ("created_at",)
    actions = [export_as_csv]


@admin.register(PromptHistory)
class PromptHistoryAdmin(admin.ModelAdmin):
    list_display = ("user_id", "product_name", "tone", "is_active", "model_used", "created_at")
    list_filter = ("is_active", "tone", "model_used", "created_at")
    search_fields = ("user_id", "product_name", "audience", "result")
    readonly_fields = ("created_at",)
    actions = [export_as_csv, soft_delete, restore_active]
    ordering = ("-created_at",)# Register your models here.
