"""
PostPress AI Views Package
Public surface for all endpoints.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Callable, Any

# Import utilities first (no circular dependency)
from .utils import VERSION, log, _json_response, _with_cors, _ppa_key_ok

# Expose urlopen at package surface so tests can monkeypatch
try:
    from urllib.request import urlopen  # type: ignore
except Exception:  # pragma: no cover
    urlopen = None  # type: ignore

__all__ = [
    "preview",
    "store", 
    "version",
    "health",
    "preview_debug_model",
    "urlopen",
    "VERSION",
]

# Optional test hook for store delegate
STORE_DELEGATE: Optional[Callable[[Any], Any]] = None

# Import view functions (these should not import back from __init__)
from .version import version
from .health import health  
from .preview import preview
from .store import store
from .debug_model import preview_debug_model

# Fix __module__ attributes for URL resolution
preview.__module__ = "postpress_ai.views"
store.__module__ = "postpress_ai.views"
version.__module__ = "postpress_ai.views"
health.__module__ = "postpress_ai.views"
preview_debug_model.__module__ = "postpress_ai.views"
