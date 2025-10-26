"""
PostPress AI — views.preview (shim)

CHANGE LOG
----------
2025-10-26 • Add preview shim module that re-exports package-level preview.  # CHANGED:

Notes
-----
This file intentionally re-exports the preview view defined at the package level
(`postpress_ai.views.preview`) to avoid duplication. URLs should continue to import
from `postpress_ai.views`, but direct imports of `.views.preview` will work too.
"""

from __future__ import annotations

# Re-export the canonical preview view from the package namespace.
# This avoids duplicate implementations and keeps a single source of truth.
from . import preview as preview  # noqa: F401

__all__ = ["preview"]
