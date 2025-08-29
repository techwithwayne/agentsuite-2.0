from django.urls import path
from humancapital.views import (
    assessment_views,
    skills_views,
    cognitive_views,
    personality_views,
    behavior_views,
    motivation_views,
    summary_views,
)

urlpatterns = [
    path("", assessment_views.welcome, name="welcome"),
    path("personal-info/", assessment_views.personal_info, name="personal_info"),
    path("skills/", skills_views.skills_form, name="skills_form"),
    path("cognitive/", cognitive_views.cognitive_form, name="cognitive_form"),
    path("personality/", personality_views.personality_form, name="personality_form"),
    path("behavior/", behavior_views.behavior_form, name="behavior_form"),
    path("motivation/", motivation_views.motivation_form, name="motivation_form"),
    path("summary/", summary_views.summary_view, name="summary_view"),
]
