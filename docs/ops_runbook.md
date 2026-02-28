# PostPress AI — Ops Runbook (Source of Truth)

## Truth sources (no guessing)
- **CODE truth:** GitHub `origin/licensing`
- **PROD truth:** Render shell + Render Postgres
- **LOCAL truth:** quick dev only (defaults to SQLite unless `DATABASE_URL` is set)

## Before you touch anything (LOCAL)
Run:
- `powershell -ExecutionPolicy Bypass -File .\tools\ppa_preflight.ps1`

Pass means:
- Git clean + synced
- Django checks OK
- Prints DB engine + license count

## Render safe key export (PROD)
```bash
export LIC_KEY="$(python manage.py shell --verbosity 0 -c 'from postpress_ai.models.license import License; print(License.objects.order_by("-id").values_list("key", flat=True).first() or "")')"
echo "LIC_KEY=${LIC_KEY:0:8}…"
```

## License sanity checks (PROD)

### BYO license must always be
- `tokens.mode = "byo"`
- `tokens.monthly_limit = 0`
- `features.byo_key_required = true`
- `features.ai_included = false`

### Tyler Early Bird promise (must never regress)
- Price: **$49/mo**
- Tokens: **120,000 / month**
- Verified on Render end-to-end via `/license/verify/` snapshot

## Debugging rule
When pasting output in chat, prefix with:
- `LOCAL:` or `RENDER:`
