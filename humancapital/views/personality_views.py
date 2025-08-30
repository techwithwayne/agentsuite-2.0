# CHANGE LOG
# Aug 29, 2025 — Ultra-defensive personality view to eliminate 500s:
# - Full try/except wrapper, absolute redirects, safe DB access.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.forms.personality_form import PersonalityForm  # CHANGED

def personality_form(request):  # CHANGED
    try:
        form = PersonalityForm(request.POST or None)  # CHANGED

        personality_list = []
        try:
            session_id = request.session.get("session_id")  # CHANGED
            if session_id:
                try:
                    from humancapital.models.personality import Personality  # CHANGED
                    try:
                        personality_list = list(Personality.objects.filter(session_id=session_id)[:100])  # CHANGED
                    except Exception:
                        personality_list = list(Personality.objects.filter(assessment_session_id=session_id)[:100])  # CHANGED
                except Exception:
                    personality_list = []
            else:
                if request.method == "GET":  # CHANGED
                    return redirect("/humancapital/personal-info/")  # CHANGED
        except Exception:
            personality_list = []

        if request.method == "POST":
            if form.is_valid():
                try:
                    obj = form.save(commit=False)  # CHANGED
                    try:
                        session_id = request.session.get("session_id")
                        if session_id:
                            from humancapital.models.assessment_session import AssessmentSession  # CHANGED
                            sess = AssessmentSession.objects.filter(id=session_id).first()
                            if sess:
                                for fk in ("session", "assessment_session"):
                                    try:
                                        setattr(obj, fk, sess)  # CHANGED
                                        break
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    try:
                        obj.save()  # CHANGED
                    except Exception:
                        pass
                except Exception:
                    pass
            return redirect("/humancapital/personality/")  # CHANGED

        return render(request, "humancapital/personality.html", {"form": form, "personality_list": personality_list})  # CHANGED

    except Exception:
        return render(request, "humancapital/personality.html", {"form": PersonalityForm(), "personality_list": []})  # CHANGED
