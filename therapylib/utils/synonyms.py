import json
import os
from functools import lru_cache

# Path to the synonyms file relative to this utils script
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "synonyms.json")

@lru_cache(maxsize=1)
def _load_synonyms():
    """Load the synonyms JSON once and cache it."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def expand_query(query: str):
    """
    Expand a search query using the synonyms dictionary.
    Returns a list of search terms (original + synonyms if found).
    """
    synonyms = _load_synonyms()
    normalized = query.lower().strip()
    expanded = [normalized]

    if normalized in synonyms:
        expanded.extend(synonyms[normalized])

    return expanded
