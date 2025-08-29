import os
import traceback
from django.shortcuts import render, redirect
from humancapital.models.assessment_session import AssessmentSession
from humancapital.services.ai_summary_service import generate_ai_summary


def summary_view(request):
    """
    Final step: Display the full assessment summary with AI-generated insights.
    Will never crash — AI errors are caught and displayed as a message.
    """

    # Debug: confirm key is being read
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("DEBUG OPENAI_API_KEY:", api_key[:10], "...(truncated)")
    else:
        print("DEBUG OPENAI_API_KEY: NOT FOUND")

    # Ensure there is an active session
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")

    session = AssessmentSession.objects.get(id=session_id)

    # Collect related assessment data
    skills = session.skills.all()
    cognitive = getattr(session, "cognitive", None)
    personality = getattr(session, "personality", None)
    behavior = getattr(session, "behavior", None)
    motivation = getattr(session, "motivation", None)

    # Default fallback message
    ai_summary = "AI summary not available at this time."

    # Try calling AI summary service safely
    try:
        ai_summary = generate_ai_summary(
            session, skills, cognitive, personality, behavior, motivation
        )
    except Exception as e:
        # Print full traceback to logs but keep app alive
        print("ERROR in AI Summary:", str(e))
        traceback.print_exc()

    # Pass everything to template
    context = {
        "session": session,
        "skills": skills,
        "cognitive": cognitive,
        "personality": personality,
        "behavior": behavior,
        "motivation": motivation,
        "ai_summary": ai_summary,
    }

    return render(request, "humancapital/summary.html", context)
