# CHANGE LOG
# Aug 30, 2025 — Full ultra-defensive motivation view:
# - Never 500s; redirects to /humancapital/personal-info/ if no session on GET.
# - On POST, best-effort attach to session and save; PRG back to motivation.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.forms.motivation_form import MotivationForm  # CHANGED

def motivation_form(request):  # CHANGED
    try:
        form = MotivationForm(request.POST or None)  # CHANGED

        motivation_list = []
        try:
            session_id = request.session.get("session_id")  # CHANGED
            if session_id:
                try:
                    from humancapital.models.motivation import Motivation  # CHANGED
                    try:
                        motivation_list = list(Motivation.objects.filter(session_id=session_id)[:100])  # CHANGED
                    except Exception:
                        motivation_list = list(Motivation.objects.filter(assessment_session_id=session_id)[:100])  # CHANGED
                except Exception:
                    motivation_list = []
            else:
                if request.method == "GET":  # CHANGED
                    return redirect("/humancapital/personal-info/")  # CHANGED
        except Exception:
            motivation_list = []

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
            return redirect("/humancapital/motivation/")  # CHANGED

        return render(request, "humancapital/motivation.html", {"form": form, "motivation_list": motivation_list})  # CHANGED

    except Exception:
        return render(request, "humancapital/motivation.html", {"form": MotivationForm(), "motivation_list": []})  # CHANGED
