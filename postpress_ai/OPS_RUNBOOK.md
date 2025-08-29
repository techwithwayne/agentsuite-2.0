# /home/techwithwayne/agentsuite/postpress_ai/OPS_RUNBOOK.md
<!--
CHANGE LOG
----------
2025-08-16
- ADD: Release Tagging & Rollback section with exact commands for creating/pushing             # CHANGED:
  a git tag for the current build (postpress-ai.v2.1-2025-08-14) and verifying it.            # CHANGED:
- ADD: Post-release verification checklist that asserts endpoint `ver` equals the tag.         # CHANGED:

2025-08-16
- NEW FILE: PostPress AI Ops Runbook with environment keys, endpoint contracts, auth/CORS,
  verification commands, troubleshooting, and rollback notes.
-->

# PostPress AI — Ops Runbook  # CHANGED:

This document is a concise checklist for deploying, verifying, and troubleshooting the **PostPress AI** service (WordPress plugin ↔ Django app).  # CHANGED:

---

## Canonical Paths & Versions  # CHANGED:
- Django project root: `~/agentsuite`  # CHANGED:
- Public views surface: `~/agentsuite/postpress_ai/views/__init__.py`  # CHANGED:
- Canonical router: `~/agentsuite/postpress_ai/urls/__init__.py`  # CHANGED:
- Legacy router: `~/agentsuite/postpress_ai/urls/routes_legacy.py`  # CHANGED:
- Version constant: `VERSION = "postpress-ai.v2.1-2025-08-14"` (returned in all endpoints)  # CHANGED:

---

## Release Tagging & Rollback (Git)  # CHANGED:

> Use annotated tags for auditable releases. Tag names must match the runtime `VERSION`.  # CHANGED:

### 1) Pre-flight  # CHANGED:
```bash
cd ~/agentsuite
git status
# Ensure clean working tree and on the intended branch (e.g., main)
grep -R "VERSION\s*=\s*\"postpress-ai.v2.1-2025-08-14\"" postpress_ai/views/__init__.py
