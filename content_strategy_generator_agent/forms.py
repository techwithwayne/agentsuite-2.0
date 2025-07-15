from django import forms
from .models import StrategyRequest

class StrategyRequestForm(forms.ModelForm):
    class Meta:
        model = StrategyRequest
        fields = ['niche', 'goals', 'tone']
        widgets = {
            'goals': forms.Textarea(attrs={'rows': 3}),
        }