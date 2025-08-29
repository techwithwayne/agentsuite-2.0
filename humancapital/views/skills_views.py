from django.shortcuts import render, redirect
from humancapital.forms.skill_form import SkillForm
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.skill import Skill


def skills_form(request):
    """
    Step 2: Capture technical/professional skills for this session.
    - GET: Show the form
    - POST: Validate and save Skill linked to the session
    """

    # Pull session from Django session (set earlier in personal_info)
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")  # fallback if session not set

    session = AssessmentSession.objects.get(id=session_id)

    if request.method == "POST":
        form = SkillForm(request.POST)
        if form.is_valid():
            # Create a Skill record tied to this assessment session
            skill = form.save(commit=False)
            skill.session = session
            skill.save()

            # For now: allow multiple skills entry
            # Redirect to same page to enter another, or later move forward
            return redirect("skills_form")
    else:
        form = SkillForm()

    # Pass existing skills to the template for display
    skills = session.skills.all()

    return render(request, "humancapital/skills.html", {"form": form, "skills": skills})
