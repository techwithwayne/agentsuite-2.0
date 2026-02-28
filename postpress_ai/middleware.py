"""postpress_ai.middleware

Ops hardening: emit build fingerprint headers.

Adds safe headers to PostPress AI endpoints:
  - X-PPA-Build: short git SHA (7 chars) when discoverable
  - X-PPA-Env:   "render" | "local" (best-effort)

No secrets are exposed.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_SHA_ENV_KEYS = (
    "PPA_BUILD_SHA",
    "RENDER_GIT_COMMIT",
    "RENDER_GIT_SHA",
    "GIT_COMMIT",
    "COMMIT_SHA",
    "SOURCE_VERSION",
    "RENDER_COMMIT",
)

def detect_env_name() -> str:
    if os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RENDER"):
        return "render"
    return "local"

def _find_repo_root(start: Path):
    p = start
    for _ in range(10):
        if (p / ".git").exists():
            return p
        if p.parent == p:
            break
        p = p.parent
    return None

@lru_cache(maxsize=1)
def get_build_sha_short() -> str:
    for k in _SHA_ENV_KEYS:
        v = (os.getenv(k) or "").strip()
        if v:
            return v[:7]

    try:
        here = Path(__file__).resolve()
        root = _find_repo_root(here)
        if root is None:
            return ""
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            timeout=0.25,
        )
        return (out.decode("utf-8", "ignore") or "").strip()[:7]
    except Exception:
        return ""

class PPABuildHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        path = getattr(request, "path", "") or ""
        if not (path.startswith("/postpress-ai/") or path.startswith("/preview/") or path.startswith("/store/")):
            return response

        sha = get_build_sha_short() or "unknown"
        env = detect_env_name()

        try:
            response["X-PPA-Build"] = sha
            response["X-PPA-Env"] = env
        except Exception:
            pass

        return response
