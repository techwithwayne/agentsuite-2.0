# -*- coding: utf-8 -*-
"""
PostPress AI — Models package entrypoint.

Why this exists:
- This app uses a models/ package (not a single models.py).
- Django discovers models when modules are imported.
- We keep your explicit exports AND we import additional modules so Django
  registers any models declared inside them.
"""

from .article import StoredArticle
from .license import License  # CHANGED:
from .activation import Activation  # CHANGED:
from .usage_event import UsageEvent  # CHANGED:

# CHANGED: Force-load additional model modules so Django sees their models.
# (We intentionally do NOT re-export their classes here unless you want that.)
from . import order  # noqa: F401  # CHANGED:
from . import customer  # noqa: F401  # CHANGED:
from . import plan  # noqa: F401  # CHANGED:
from . import subscription  # noqa: F401  # CHANGED:
from . import entitlement  # noqa: F401  # CHANGED:
from . import credit  # noqa: F401  # CHANGED:
from . import email_log  # noqa: F401  # CHANGED:
from . import usage_event  # noqa: F401  # CHANGED:

__all__ = [
    "StoredArticle",
    "License",     # CHANGED:
    "Activation",  # CHANGED:
    "UsageEvent",  # CHANGED:
]  # CHANGED:
