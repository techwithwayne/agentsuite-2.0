# /home/techwithwayne/agentsuite/agentsuite/wsgi.py

"""
Agentsuite WSGI config

CHANGE LOG
----------
2026-02-21 • RENDER FIX: Ensure `application` exists for gunicorn agentsuite.wsgi:application.  # CHANGED:
"""

import os  # CHANGED:

from django.core.wsgi import get_wsgi_application  # CHANGED:

# Gunicorn expects this module to expose `application`.  # CHANGED:
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agentsuite.settings")  # CHANGED:

application = get_wsgi_application()  # CHANGED: