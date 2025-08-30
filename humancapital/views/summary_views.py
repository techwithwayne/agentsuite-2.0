# CHANGE LOG
# Aug 29, 2025 — Ultra-defensive summary view to eliminate 500s:
# - Full try/except wrapper; redirects if no session on GET.
# - AI summary uses env-gated fallback and never raises.

from django.shortcuts import render, redirect  # CHANGED
from humancapital.services.ai_summary_service import generate_ai_summary  # CHANGED

def summary_view(request):  # CHANGED
    try:
        session_id = request.session.get("session_id")  # CHANGED
        if not session_id:
            if request.method == "GET":  # CHANGED
                return redirect("/humancapital/personal-info/")  # CHANGED

        # Best-effort fetch of session (optional)
        session = None
        try:
            if session_id:
                from humancapital.models.assessment_session import AssessmentSession  # CHANGED
                session = AssessmentSession.objects.filter(id=session_id).first()
        except Exception:
            session = None

        # Use stored ai_summary if available
        ai_summary = ""
        try:
            if session and getattr(session, "ai_summary", ""):
                ai_summary = session.ai_summary  # CHANGED
        except Exception:
            ai_summary = ""

        if not ai_summary:
            try:
                ai_summary = generate_ai_summary(session)  # CHANGED
                if session and ai_summary:
                    try:
                        session.ai_summary = ai_summary  # CHANGED
                        session.save(update_fields=["ai_summary"])  # CHANGED
                    except Exception:
                        pass
            except Exception:
                ai_summary = "Summary unavailable."  # CHANGED

        ctx = {"session": session, "ai_summary": ai_summary or "Summary unavailable."}  # CHANGED
        return render(request, "humancapital/summary.html", ctx)  # CHANGED

    except Exception:
        # Absolute fallback render
        return render(request, "humancapital/summary.html", {"session": None, "ai_summary": "Summary unavailable."})  # CHANGED
