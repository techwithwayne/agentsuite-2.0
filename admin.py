# humancapital/admin.py
from django.contrib import admin

# Import each model directly to avoid relying on __init__ exports
from .models.assessment_session import AssessmentSession
from .models.user_profile import UserProfile
from .models.skill import Skill
from .models.cognitive import CognitiveAbility
from .models.personality import Personality
from .models.behavior import Behavior
from .models.motivation import Motivation


class SafeColumnsMixin:
    """Helpers for list_display that won't break if fields differ per model."""

    @admin.display(description="Session")
    def _session(self, obj):
        # Common patterns across our models
        return (
            getattr(obj, "session", None)
            or getattr(obj, "assessment_session", None)
            or "-"
        )

    @admin.display(description="Label")
    def _label(self, obj):
        # Try a series of likely attribute names
        for attr in ("name", "label", "trait", "behavior", "factor", "metric", "skill", "title"):
            val = getattr(obj, attr, None)
            if val:
                return val
        # Fallback to __str__
        return str(obj)

    @admin.display(description="Level/Score")
    def _level(self, obj):
        for attr in ("level", "score", "value", "rating"):
            val = getattr(obj, attr, None)
            if val is not None:
                return val
        return "-"

    @admin.display(description="Updated")
    def _updated(self, obj):
        # Display some notion of recency if present
        for attr in ("updated_at", "modified", "modified_at", "created_at", "created", "timestamp"):
            val = getattr(obj, attr, None)
            if val:
                return val
        return "-"


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_label", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(UserProfile)
class UserProfileAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_label", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(Skill)
class SkillAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_session", "_label", "_level", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(CognitiveAbility)
class CognitiveAbilityAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_session", "_label", "_level", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(Personality)
class PersonalityAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_session", "_label", "_level", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(Behavior)
class BehaviorAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_session", "_label", "_level", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)


@admin.register(Motivation)
class MotivationAdmin(SafeColumnsMixin, admin.ModelAdmin):
    list_display = ("id", "_session", "_label", "_level", "_updated")
    search_fields = ("id",)
    ordering = ("-id",)
