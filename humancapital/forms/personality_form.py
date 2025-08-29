from django import forms
from humancapital.models.personality import Personality


class PersonalityForm(forms.ModelForm):
    """
    Form for capturing Big Five (OCEAN) personality trait scores.
    Each trait is scored on a 0–100 scale.
    """

    openness = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Openness",
        help_text="Openness to new experiences (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    conscientiousness = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Conscientiousness",
        help_text="Organization and dependability (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    extraversion = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Extraversion",
        help_text="Sociability and energy orientation (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    agreeableness = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Agreeableness",
        help_text="Compassion and cooperativeness (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    neuroticism = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Neuroticism",
        help_text="Emotional stability (0–100, higher = more unstable)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    class Meta:
        model = Personality
        fields = [
            "openness",
            "conscientiousness",
            "extraversion",
            "agreeableness",
            "neuroticism",
            "notes",
        ]

        widgets = {
            "notes": forms.Textarea(attrs={"placeholder": "Optional notes (AI or evaluator)", "rows": 3}),
        }
