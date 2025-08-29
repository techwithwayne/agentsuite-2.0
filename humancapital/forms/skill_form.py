from django import forms
from humancapital.models.skill import Skill


class SkillForm(forms.ModelForm):
    """
    Form for capturing a single skill rating inside an assessment.
    Example: "Python" -> Rating: 4/5
    """

    # Override the rating field with a Likert-style dropdown (1 = beginner, 5 = expert).
    rating = forms.ChoiceField(
        choices=[(i, str(i)) for i in range(1, 6)],  # 1–5 scale
        widget=forms.RadioSelect,  # Render as radio buttons for clarity
        label="Proficiency Rating",
    )

    class Meta:
        model = Skill
        fields = ["category", "name", "rating", "weight"]

        widgets = {
            "category": forms.TextInput(attrs={"placeholder": "Skill Category (e.g., Programming)"}),
            "name": forms.TextInput(attrs={"placeholder": "Skill Name (e.g., Python, SQL)"}),
            "weight": forms.NumberInput(attrs={"step": 0.1, "min": 0.1, "max": 5}),
        }
