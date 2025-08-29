# forms.py — adds helpful placeholders for niche, goals, tone.
from django import forms

# Prefer ModelForm if you have a StrategyRequest model; otherwise fall back to a plain Form.
try:
    from .models import StrategyRequest  # adjust if your model lives elsewhere

    class StrategyRequestForm(forms.ModelForm):
        class Meta:
            model = StrategyRequest
            fields = ["niche", "goals", "tone"]
            widgets = {
                "niche": forms.TextInput(attrs={
                    "placeholder": "e.g., Local vegan bakery in Austin",
                    "class": "cg-input"
                }),
                "goals": forms.Textarea(attrs={
                    "rows": 3,
                    "placeholder": "e.g., Grow newsletter to 5k, +20% online orders, rank for “vegan cupcakes Austin”",
                    "class": "cg-textarea"
                }),
                "tone": forms.TextInput(attrs={
                    "placeholder": "e.g., Friendly, witty, expert-but-approachable",
                    "class": "cg-input"
                }),
            }

except Exception:
    # Fallback that works without a model
    class StrategyRequestForm(forms.Form):
        niche = forms.CharField(
            label="Niche",
            widget=forms.TextInput(attrs={
                "placeholder": "e.g., Local vegan bakery in Austin",
                "class": "cg-input"
            })
        )
        goals = forms.CharField(
            label="Goals",
            widget=forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "e.g., Grow newsletter to 5k, +20% online orders, rank for “vegan cupcakes Austin”",
                "class": "cg-textarea"
            })
        )
        tone = forms.CharField(
            label="Tone",
            widget=forms.TextInput(attrs={
                "placeholder": "e.g., Friendly, witty, expert-but-approachable",
                "class": "cg-input"
            })
        )
