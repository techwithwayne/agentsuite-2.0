from django import forms
from humancapital.models.cognitive import CognitiveAbility


class CognitiveForm(forms.ModelForm):
    """
    Form for capturing cognitive ability scores for a session.
    Includes reasoning, memory, problem-solving, and attention.
    Each scored on a 0–100 scale.
    """

    reasoning = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Reasoning",
        help_text="Logical reasoning score (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    memory = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Memory",
        help_text="Memory retention score (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    problem_solving = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Problem Solving",
        help_text="Ability to solve problems (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    attention = forms.IntegerField(
        min_value=0,
        max_value=100,
        label="Attention",
        help_text="Attention and focus (0–100)",
        widget=forms.NumberInput(attrs={"placeholder": "0–100"})
    )

    class Meta:
        model = CognitiveAbility
        fields = ["reasoning", "memory", "problem_solving", "attention", "notes"]

        widgets = {
            "notes": forms.Textarea(attrs={"placeholder": "Optional evaluator/AI notes", "rows": 3}),
        }
