from django.shortcuts import render, redirect
from humancapital.forms.cognitive_form import CognitiveForm
from humancapital.models.assessment_session import AssessmentSession
from humancapital.models.cognitive import CognitiveAbility


def cognitive_form(request):
    """
    Step 3: Capture cognitive ability scores for this session.
    - GET: Show the form
    - POST: Validate and save CognitiveAbility linked to the session
    """

    # Ensure a session exists
    session_id = request.session.get("session_id")
    if not session_id:
        return redirect("personal_info")  # fallback if session not set

    session = AssessmentSession.objects.get(id=session_id)

    if request.method == "POST":
        form = CognitiveForm(request.POST)
        if form.is_valid():
            # Create a CognitiveAbility record tied to this assessment session
            cognitive = form.save(commit=False)
            cognitive.session = session
            cognitive.save()

            # Move forward to Personality step (next in flow)
            return redirect("personality_form")
    else:
        form = CognitiveForm()

    return render(request, "humancapital/cognitive.html", {"form": form})
