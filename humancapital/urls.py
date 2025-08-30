# CHANGE LOG
# Aug 29, 2025 — Add app_name + explicit routes so namespaced reverses work.

from django.urls import path

from humancapital.views.assessment_views import welcome, personal_info
from humancapital.views.skills_views import skills_form
from humancapital.views.cognitive_views import cognitive_form
from humancapital.views.personality_views import personality_form
from humancapital.views.behavior_views import behavior_form
from humancapital.views.motivation_views import motivation_form
from humancapital.views.summary_views import summary_view

app_name = "humancapital"  # CHANGED

urlpatterns = [
    path("welcome/", welcome, name="welcome"),
    path("personal-info/", personal_info, name="personal_info"),
    path("skills/", skills_form, name="skills"),
    path("cognitive/", cognitive_form, name="cognitive"),
    path("personality/", personality_form, name="personality"),
    path("behavior/", behavior_form, name="behavior"),
    path("motivation/", motivation_form, name="motivation"),
    path("summary/", summary_view, name="summary"),
]
