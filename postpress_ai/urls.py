# /home/techwithwayne/agentsuite/postpress_ai/urls.py
"""
PostPress AI — URL routes (loader shim)

WHY THIS FILE EXISTS
--------------------
Django projects commonly include "postpress_ai.urls" at the module path.

This repo also uses a package router at:
    postpress_ai/urls/__init__.py

To prevent routing ambiguity (module vs package) and keep imports deterministic,
this module becomes a thin re-export of the package router's urlpatterns.

CHANGE LOG
----------
2025-12-24
- FIX: Convert urls.py into a deterministic re-export shim for postpress_ai.urls package router.  # CHANGED:
- KEEP: No routing logic lives here; canonical patterns live in postpress_ai/urls/__init__.py.   # CHANGED:
"""

from __future__ import annotations

# Re-export canonical urlpatterns from the package router.  # CHANGED:
from postpress_ai.urls import urlpatterns as urlpatterns  # type: ignore  # CHANGED:

# Preserve namespaced include expectations.  # CHANGED:
app_name = "postpress_ai"  # CHANGED:
