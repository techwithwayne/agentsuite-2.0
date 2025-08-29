from django.shortcuts import render, redirect
from humancapital.forms.personal_info_form import PersonalInfoForm
from humancapital.models.user_profile import UserProfile
from humancapital.models.assessment_session import AssessmentSession


def welcome(request):
    """
    First page of the assessment.
    Displays a simple welcome screen with a button to start the process.
    """
    return render(request, "humancapital/welcome.html")


def personal_info(request):
    """
    Handles the personal info form (UserProfile).
    - GET: Show the empty form
    - POST: Validate, save UserProfile, create an AssessmentSession, then redirect
    """
    if request.method == "POST":
        form = PersonalInfoForm(request.POST)
        if form.is_valid():
            # Save the new user profile
            profile = form.save()

            # Create an assessment session for this user
            session = AssessmentSession.objects.create(user=profile)

            # Store session ID in Django session so we can continue later
            request.session["session_id"] = session.id

            # Redirect to the skills step next (will be created later)
            return redirect("skills_form")
    else:
        form = PersonalInfoForm()

    return render(request, "humancapital/personal_info.html", {"form": form})
