import os
from functools import lru_cache
from django.core.exceptions import ImproperlyConfigured
from openai import OpenAI

@lru_cache
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Don’t kill Django startup; raise only when actually called by a request
        raise ImproperlyConfigured("OPENAI_API_KEY is missing")
    return OpenAI(api_key=api_key)
