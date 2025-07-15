from django import forms

class URLScanForm(forms.Form):
    url = forms.URLField(label='Website URL', max_length=255)