"""
postpress_ai.license_keys

License key generation utilities for PostPress AI (Django authoritative).

Design goals:
- Human-friendly keys (no confusing chars like O/0, I/1, etc.)
- High entropy (cryptographically secure randomness via `secrets`)
- Easy to validate/format consistently
- Optional uniqueness loop (caller provides an `exists()` callback)

Format (default):
  PPA-XXXXX-XXXXX-XXXXX-XXXXX

Where X uses an unambiguous alphabet:
  23456789ABCDEFGHJKLMNPQRSTUVWXYZ
(omits: 0,1,I,O)

========= CHANGE LOG =========
2025-12-26 • ADD: Secure, unambiguous license key generator + uniqueness helper.  # CHANGED:
"""

from __future__ import annotations

import secrets
from typing import Callable, Optional


# Unambiguous, uppercase, no 0/1/I/O to reduce support issues.  # CHANGED:
ALPHABET: str = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # CHANGED:


def generate_license_key(  # CHANGED:
    *,
    prefix: str = "PPA",
    groups: int = 4,
    group_len: int = 5,
) -> str:
    """
    Generate a single license key string.

    Example:
      PPA-7K4Q9-9R6G2-2XQ8M-H7D5P
    """
    pfx = (prefix or "").strip().upper()
    if not pfx:
        pfx = "PPA"

    if groups < 1:
        groups = 1
    if group_len < 4:
        # Keep groups reasonably long to avoid weak keys.  # CHANGED:
        group_len = 4

    chunks = []
    for _ in range(groups):
        chunks.append("".join(secrets.choice(ALPHABET) for _ in range(group_len)))

    return f"{pfx}-" + "-".join(chunks)


def generate_unique_license_key(  # CHANGED:
    *,
    exists: Callable[[str], bool],
    prefix: str = "PPA",
    groups: int = 4,
    group_len: int = 5,
    max_tries: int = 25,
) -> str:
    """
    Generate a license key and ensure it does not already exist.

    `exists(key) -> bool` must be provided by the caller (typically:
      lambda k: License.objects.filter(key=k).exists()
    )

    We cap attempts to avoid infinite loops under unexpected conditions.
    """
    if max_tries < 1:
        max_tries = 1

    last: Optional[str] = None
    for _ in range(max_tries):
        candidate = generate_license_key(prefix=prefix, groups=groups, group_len=group_len)
        last = candidate
        try:
            if not exists(candidate):
                return candidate
        except Exception:
            # If the exists-check fails, do NOT silently issue a key.  # CHANGED:
            raise

    raise RuntimeError(f"Unable to generate unique license key after {max_tries} tries. Last={last}")
