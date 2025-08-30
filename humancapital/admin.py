# CHANGE LOG
# Aug 30, 2025 — Admin polish:
# - Inlines for related models
# - ai_summary read-only
# - Chart.js snapshot on session change page
# - Custom POST endpoint: "Regenerate summary"
# - CHANGED: Safe list_display accessors (avoid 500 if model lacks created_at/updated_at)

from django.contrib import admin, messages
from django.urls import path, reverse
from django.shortcuts import redirect, get_object_or_404
from django.core.exceptions import PermissionDenied

from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.skill import Skill
from humancapital.models.cognitive import CognitiveAbility
from humancapital.models.personality import Personality
from humancapital.models.behavior import Behavior
from humancapital.models.motivation import Motivation


# ----- Inlines -----
class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0
    show_change_link = True


class CognitiveInline(admin.TabularInline):
    model = CognitiveAbility
    extra = 0
    show_change_link = True


class PersonalityInline(admin.TabularInline):
    model = Personality
    extra = 0
    show_change_link = True


class BehaviorInline(admin.TabularInline):
    model = Behavior
    extra = 0
    show_change_link = True


class MotivationInline(admin.TabularInline):
    model = Motivation
    extra = 0
    show_change_link = True


def _safe_count(rel_manager):
    try:
        return rel_manager.count()
    except Exception:
        try:
            return len(list(rel_manager.all()))
        except Exception:
            return 0


def _rel_count(obj, candidates):
    for name in candidates:
        try:
            rel = getattr(obj, name)
        except Exception:
            rel = None
        if rel is not None:
            c = _safe_count(rel)
            if c >= 0:
                return c
    return 0


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    change_form_template = "admin/humancapital/assessmentsession/change_form.html"
    readonly_fields = ("ai_summary",)

    # CHANGED: Use safe methods instead of raw field names to avoid 500s
    list_display = ("id", "created_ts", "updated_ts")

    search_fields = ("id",)
    inlines = [SkillInline, CognitiveInline, PersonalityInline, BehaviorInline, MotivationInline]

    # --- Safe accessors so missing fields won't 500 the changelist ---
    def created_ts(self, obj):
        for name in ("created_at", "created", "created_on", "timestamp"):
            val = getattr(obj, name, None)
            if val:
                return val
        return ""

    created_ts.short_description = "Created"

    def updated_ts(self, obj):
        for name in ("updated_at", "updated", "modified_at", "modified"):
            val = getattr(obj, name, None)
            if val:
                return val
        # Fall back to created value if no explicit updated
        return self.created_ts(obj)

    updated_ts.short_description = "Updated"

    # --- Custom admin URL: regenerate summary for a single session ---
    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path(
                "<path:object_id>/regenerate-summary/",
                self.admin_site.admin_view(self.regenerate_summary),
                name="humancapital_assessmentsession_regen",
            )
        ]
        return my_urls + urls

    def regenerate_summary(self, request, object_id, *args, **kwargs):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            return redirect(reverse("admin:humancapital_assessmentsession_change", args=[object_id]))

        obj = get_object_or_404(AssessmentSession, pk=object_id)

        from humancapital.services.ai_summary_service import generate_ai_summary, DISABLED

        try:
            text = generate_ai_summary(obj)
            obj.ai_summary = text
            obj.save(update_fields=["ai_summary"])
            note = "AI summary regenerated."
            if DISABLED:
                note += " (AI disabled; fallback text saved.)"
            messages.success(request, note)
        except Exception as e:
            messages.error(request, f"Could not regenerate summary: {e}")

        return redirect(reverse("admin:humancapital_assessmentsession_change", args=[object_id]))


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "level")
    search_fields = ("name",)


@admin.register(CognitiveAbility)
class CognitiveAbilityAdmin(admin.ModelAdmin):
    list_display = ("id", "metric", "score")
    search_fields = ("metric",)


@admin.register(Personality)
class PersonalityAdmin(admin.ModelAdmin):
    list_display = ("id", "trait", "level")
    search_fields = ("trait",)


@admin.register(Behavior)
class BehaviorAdmin(admin.ModelAdmin):
    list_display = ("id", "behavior", "level")
    search_fields = ("behavior",)


@admin.register(Motivation)
class MotivationAdmin(admin.ModelAdmin):
    list_display = ("id", "factor", "level")
    search_fields = ("factor",)
