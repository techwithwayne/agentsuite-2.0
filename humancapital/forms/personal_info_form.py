from django import forms
from humancapital.models.user_profile import UserProfile


class PersonalInfoForm(forms.ModelForm):
    """
    Form for capturing personal and professional details about a user.
    This ties directly to the UserProfile model.
    """

    class Meta:
        model = UserProfile  # Link form to UserProfile model
        fields = [
            "full_name",
            "email",
            "age",
            "job_title",
            "industry",
        ]  # Only expose these fields in the form

        # Optional: customize widget styles (can be expanded later for better UI)
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "Full Name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email Address"}),
            "age": forms.NumberInput(attrs={"min": 16, "max": 100}),
            "job_title": forms.TextInput(attrs={"placeholder": "Job Title"}),
            "industry": forms.TextInput(attrs={"placeholder": "Industry"}),
        }
