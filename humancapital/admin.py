"""
CHANGE LOG:
- Removed duplicate `admin.site.register(AssessmentSession)`.
- All models registered cleanly with `@admin.register`.
- Added inline admins for Skills, Cognitive, Personality, Behavior, Motivation so everything shows up in AssessmentSession.
"""

from django.contrib import admin
from humancapital.models.user_profile import UserProfile
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.skill import Skill
from humancapital.models.cognitive import CognitiveAbility
from humancapital.models.personality import Personality
from humancapital.models.behavior import Behavior
from humancapital.models.motivation import Motivation


# ----------------------------
# Inline Classes
# ----------------------------

class SkillInline(admin.TabularInline):
    model = Skill
    extra = 0
    fields = ("category", "name", "rating", "weight", "created_at")
    readonly_fields = ("created_at",)


class CognitiveAbilityInline(admin.TabularInline):
    model = CognitiveAbility
    extra = 0
    fields = ("reasoning", "memory", "problem_solving", "attention", "notes", "created_at")
    readonly_fields = ("created_at",)


class PersonalityInline(admin.TabularInline):
    model = Personality
    extra = 0
    fields = (
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "notes",
        "created_at",
    )
    readonly_fields = ("created_at",)


class BehaviorInline(admin.TabularInline):
    model = Behavior
    extra = 0
    fields = (
        "communication",
        "decision_making",
        "leadership",
        "collaboration",
        "conflict_handling",
        "notes",
        "created_at",
    )
    readonly_fields = ("created_at",)


class MotivationInline(admin.TabularInline):
    model = Motivation
    extra = 0
    fields = ("achievement", "stability", "autonomy", "recognition", "learning", "notes", "created_at")
    readonly_fields = ("created_at",)


# ----------------------------
# Admin Registrations
# ----------------------------

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "email", "created_at")
    search_fields = ("full_name", "email")
    list_filter = ("created_at",)


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_profile",
        "started_at",
        "completed_at",
        "ai_summary",
    )
    list_filter = ("completed_at", "started_at")
    search_fields = ("user_profile__full_name",)
    readonly_fields = ("ai_summary",)

    inlines = [SkillInline, CognitiveAbilityInline, PersonalityInline, BehaviorInline, MotivationInline]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "category", "name", "rating", "weight", "created_at")
    list_filter = ("category", "rating")
    search_fields = ("name", "category")


@admin.register(CognitiveAbility)
class CognitiveAbilityAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "reasoning", "memory", "problem_solving", "attention", "created_at")
    list_filter = ("reasoning", "memory", "problem_solving", "attention")
    search_fields = ("session__id",)


@admin.register(Personality)
class PersonalityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "created_at",
    )
    list_filter = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
    search_fields = ("session__id",)


@admin.register(Behavior)
class BehaviorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "communication",
        "decision_making",
        "leadership",
        "collaboration",
        "conflict_handling",
        "created_at",
    )
    list_filter = ("communication", "decision_making", "leadership", "collaboration", "conflict_handling")
    search_fields = ("session__id",)


@admin.register(Motivation)
class MotivationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session",
        "achievement",
        "stability",
        "autonomy",
        "recognition",
        "learning",
        "created_at",
    )
    list_filter = ("achievement", "stability", "autonomy", "recognition", "learning")
    search_fields = ("session__id",)
