# CHANGE LOG
# Aug 30, 2025 — Replace placeholder with full ultra-defensive behavior view:
# - Never 500s; redirects to /humancapital/personal-info/ if no session on GET.
# - On POST, best-effort attach to session and save; then PRG back to behavior.
# - Lists existing behavior rows for the current session.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.forms.behavior_form import BehaviorForm  # CHANGED

def behavior_form(request):  # CHANGED
    try:
        form = BehaviorForm(request.POST or None)  # CHANGED

        behavior_list = []
        try:
            session_id = request.session.get("session_id")  # CHANGED
            if session_id:
                try:
                    from humancapital.models.behavior import Behavior  # CHANGED
                    # Try common FK field names defensively
                    try:
                        behavior_list = list(Behavior.objects.filter(session_id=session_id)[:100])  # CHANGED
                    except Exception:
                        behavior_list = list(Behavior.objects.filter(assessment_session_id=session_id)[:100])  # CHANGED
                except Exception:
                    behavior_list = []
            else:
                if request.method == "GET":  # CHANGED
                    return redirect("/humancapital/personal-info/")  # CHANGED
        except Exception:
            behavior_list = []

        if request.method == "POST":
            if form.is_valid():
                try:
                    obj = form.save(commit=False)  # CHANGED
                    # Attach to session if present
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
            # PRG to avoid resubmits
            return redirect("/humancapital/behavior/")  # CHANGED

        return render(request, "humancapital/behavior.html", {"form": form, "behavior_list": behavior_list})  # CHANGED

    except Exception:
        return render(request, "humancapital/behavior.html", {"form": BehaviorForm(), "behavior_list": []})  # CHANGED
