from django import forms
from humancapital.models.behavior import Behavior


class BehaviorForm(forms.ModelForm):
    """
    Form for capturing behavioral style indicators.
    Includes communication, decision-making, leadership,
    collaboration, and conflict handling.
    Each trait scored on a 0–100 scale.
    """

    communication = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Communication",
        help_text="Clarity and style of communication (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    decision_making = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Decision Making",
        help_text="Speed and confidence in decisions (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    leadership = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Leadership",
        help_text="Leadership vs. support orientation (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    collaboration = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Collaboration",
        help_text="Ability to collaborate effectively (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    conflict_handling = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Conflict Handling",
        help_text="Approach to managing conflict (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    class Meta:
        model = Behavior
        fields = [
            "communication",
            "decision_making",
            "leadership",
            "collaboration",
            "conflict_handling",
            "notes",
        ]

        widgets = {
            "notes": forms.Textarea(attrs={"placeholder": "Optional notes (AI or evaluator)", "rows": 3}),
        }
