"""
PostPress AI — Models Loader (Shim)

WHY THIS FILE EXISTS
--------------------
Django auto-discovers models from `app/models.py`. Your project keeps real models in the
`postpress_ai/models/` package (e.g., models/article.py). This shim imports those models
so Django sees them consistently (migrations/admin/ORM).

========= CHANGE LOG =========
2025-12-26 • PREP: Add forward-compatible imports for Stripe fulfillment models (Order, License).  # CHANGED:
           • Keep safe-import pattern (no hard crash if files not present yet).                    # CHANGED:
2025-12-24 • Convert models.py into a safe loader shim for package-based models.                   # CHANGED:
           • Import StoredArticle from postpress_ai/models/article.py.                            # CHANGED:
           • Add forward-compatible imports for License/Activation modules (no break if absent).  # CHANGED:
"""

# NOTE: Do NOT import models inside AppConfig.ready(); keep model loading deterministic.  # CHANGED:

# Import the package-exported models so Django registers them.  # CHANGED:
# Your `postpress_ai/models/__init__.py` currently exports StoredArticle.  # CHANGED:
try:  # CHANGED:
    from .models import StoredArticle  # noqa: F401  # CHANGED:
except Exception:  # CHANGED:
    # If the package layout changes during refactors, avoid hard crash on import.  # CHANGED:
    # We’ll tighten this once the fulfillment/licensing modules are in place.  # CHANGED:
    StoredArticle = None  # type: ignore  # CHANGED:


# Forward-compatible: once you add these files, Django will pick them up automatically via this shim.  # CHANGED:
# Planned files:
# - postpress_ai/models/order.py
# - postpress_ai/models/license.py
# - postpress_ai/models/activation.py  (optional / legacy)
try:  # CHANGED:
    from .models.order import Order  # noqa: F401  # CHANGED:
except Exception:  # CHANGED:
    Order = None  # type: ignore  # CHANGED:

try:  # CHANGED:
    from .models.license import License  # noqa: F401  # CHANGED:
except Exception:  # CHANGED:
    License = None  # type: ignore  # CHANGED:

try:  # CHANGED:
    from .models.activation import Activation  # noqa: F401  # CHANGED:
except Exception:  # CHANGED:
    Activation = None  # type: ignore  # CHANGED:
