# tools/ppa_preflight.ps1
# Run from repo root. Fails fast if anything is off.

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== PPA PREFLIGHT (LOCAL) ==="
Write-Host "PWD: $(Get-Location)"

# 1) Git sanity
git fetch --all --prune | Out-Null

$branch = (git branch --show-current).Trim()
if ($branch -ne "licensing") { throw "Wrong branch: $branch (expected licensing)" }

$status = (git status -sb)
Write-Host $status
if ($status -match "ahead|behind|\?\?| M | D ") { throw "Working tree not clean or not synced. Fix git status first." }

$head = (git rev-parse --short HEAD).Trim()
$orig = (git rev-parse --short origin/licensing).Trim()
if ($head -ne $orig) { throw "HEAD ($head) != origin/licensing ($orig)" }

Write-Host "Git OK: $branch @ $head"

# 2) Django check
python manage.py check | Out-Host

# 3) DB target + basic data signal
python manage.py shell --verbosity 0 -c "from django.conf import settings; d=settings.DATABASES['default']; print('DB_ENGINE='+str(d.get('ENGINE'))); print('DB_NAME='+str(d.get('NAME'))); print('DB_HOST='+str(d.get('HOST')));" | Out-Host
python manage.py shell --verbosity 0 -c "from postpress_ai.models.license import License; print('LICENSE_COUNT='+str(License.objects.count()))" | Out-Host

Write-Host "=== PREFLIGHT PASS ==="
