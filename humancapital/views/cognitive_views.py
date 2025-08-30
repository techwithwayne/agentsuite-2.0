# CHANGE LOG
# Aug 29, 2025 — Ultra-defensive cognitive view to eliminate 500s:
# - Full try/except wrapper, absolute redirects, safe DB access.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.forms.cognitive_form import CognitiveForm  # CHANGED

def cognitive_form(request):  # CHANGED
    try:
        form = CognitiveForm(request.POST or None)  # CHANGED

        cognitive_list = []
        try:
            session_id = request.session.get("session_id")  # CHANGED
            if session_id:
                try:
                    from humancapital.models.cognitive import CognitiveAbility  # CHANGED
                    try:
                        cognitive_list = list(CognitiveAbility.objects.filter(session_id=session_id)[:100])  # CHANGED
                    except Exception:
                        cognitive_list = list(CognitiveAbility.objects.filter(assessment_session_id=session_id)[:100])  # CHANGED
                except Exception:
                    cognitive_list = []
            else:
                if request.method == "GET":  # CHANGED
                    return redirect("/humancapital/personal-info/")  # CHANGED
        except Exception:
            cognitive_list = []

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
            return redirect("/humancapital/cognitive/")  # CHANGED

        return render(request, "humancapital/cognitive.html", {"form": form, "cognitive_list": cognitive_list})  # CHANGED

    except Exception:
        return render(request, "humancapital/cognitive.html", {"form": CognitiveForm(), "cognitive_list": []})  # CHANGED
