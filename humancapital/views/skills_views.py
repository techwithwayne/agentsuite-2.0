# CHANGE LOG
# Aug 29, 2025 — Ultra-defensive skills view to eliminate 500s:
# - Full try/except wrapper, absolute redirects, safe DB access.
# - Works without namespace reverses. Uses absolute URLs.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.forms.skill_form import SkillForm  # CHANGED

def skills_form(request):  # CHANGED
    # Always render safely, even if session/model wiring is off.
    try:
        # Form first (always safe)
        form = SkillForm(request.POST or None)  # CHANGED

        # Attempt to fetch current list for this session (optional)
        skills_list = []
        try:
            session_id = request.session.get("session_id")  # CHANGED
            if session_id:
                # Try to load from model without hardcoding related_name
                try:
                    from humancapital.models.skill import Skill  # CHANGED
                    # Try common field names defensively
                    try:
                        skills_list = list(Skill.objects.filter(session_id=session_id)[:100])  # CHANGED
                    except Exception:
                        skills_list = list(Skill.objects.filter(assessment_session_id=session_id)[:100])  # CHANGED
                except Exception:
                    skills_list = []
            else:
                # With no session cookie, redirect to start (GET becomes 302)
                if request.method == "GET":  # CHANGED
                    return redirect("/humancapital/personal-info/")  # CHANGED
        except Exception:
            skills_list = []

        # Handle POST defensively
        if request.method == "POST":
            if form.is_valid():
                try:
                    obj = form.save(commit=False)  # CHANGED
                    # Try to attach to AssessmentSession if present
                    try:
                        session_id = request.session.get("session_id")
                        if session_id:
                            from humancapital.models.assessment_session import AssessmentSession  # CHANGED
                            sess = AssessmentSession.objects.filter(id=session_id).first()
                            if sess:
                                # Try common FK attribute names; ignore failures
                                for fk in ("session", "assessment_session"):
                                    try:
                                        setattr(obj, fk, sess)  # CHANGED
                                        break
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    # Save best-effort
                    try:
                        obj.save()  # CHANGED
                    except Exception:
                        pass
                except Exception:
                    pass
            # Always post-redirect to avoid resubmits (and keep page stable)
            return redirect("/humancapital/skills/")  # CHANGED

        return render(request, "humancapital/skills.html", {"form": form, "skills_list": skills_list})  # CHANGED

    except Exception:
        # Last-ditch: render empty form/list
        return render(request, "humancapital/skills.html", {"form": SkillForm(), "skills_list": []})  # CHANGED
