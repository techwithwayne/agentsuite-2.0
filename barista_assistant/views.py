from django.shortcuts import render

from django.http import HttpResponse

def index(request):
    return render(request, 'barista_assistant/base.html')

def success_view(request):
    return render(request, 'barista_assistant/success.html')

def cancel_view(request):
    return render(request, 'barista_assistant/cancel.html')
