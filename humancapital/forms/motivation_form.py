from django import forms
from humancapital.models.motivation import Motivation


class MotivationForm(forms.ModelForm):
    """
    Form for capturing motivational drivers.
    Includes intrinsic and extrinsic motivators:
    - Achievement, Stability, Autonomy, Recognition, Learning
    Each is rated on a 0–100 scale.
    """

    achievement = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Achievement",
        help_text="Drive for success and results (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    stability = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Stability",
        help_text="Need for security and consistency (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    autonomy = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Autonomy",
        help_text="Desire for independence and freedom (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    recognition = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Recognition",
        help_text="Need for praise and visibility (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    learning = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Learning",
        help_text="Motivation to learn and grow (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    class Meta:
        model = Motivation
        fields = [
            "achievement",
            "stability",
            "autonomy",
            "recognition",
            "learning",
            "notes",
        ]

        widgets = {
            "notes": forms.Textarea(attrs={"placeholder": "Optional notes (AI or evaluator)", "rows": 3}),
        }
