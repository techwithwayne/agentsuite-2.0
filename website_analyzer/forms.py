from django import forms

class URLScanForm(forms.Form):
    url = forms.URLField(
        label='',
        max_length=255,
        widget=forms.URLInput(attrs={
            "placeholder": "Website URL",
            "class": "wa-input",
            "autocomplete": "off",
            "inputmode": "url",
            "aria-label": "Website URL",
        })
    )
