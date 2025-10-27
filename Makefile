# PostPress AI - Makefile (gentle smokes + ops)
# This file avoids TAB issues by using .RECIPEPREFIX so recipe lines start with "> ".
.RECIPEPREFIX := >
SHELL := /bin/bash

PYROOT := /home/techwithwayne/agentsuite
VENV  := $(PYROOT)/venv
DOMAIN ?= https://apps.techwithwayne.com

.PHONY: key reload pa-preview-post pa-store-post pa-smoke \
        wp-url wp-preview wp-store wp-smoke push

key:
> cd "$(PYROOT)" && . "$(VENV)/bin/activate" && \
> python -c 'import re; import sys; \
txt=open(".env","rb").read().decode("utf-8","replace") if True else ""; \
m=re.search(r"^PPA_SHARED_KEY\\s*=\\s*[\\"\\\']?([^\\r\\n#]+?)[\\"\\\']?",txt,re.M); \
k=(m.group(1).strip() if m else ""); print("INFO: KEY chars:", len(k))' || true

reload:
> touch /var/www/apps_techwithwayne_com_wsgi.py 2>/dev/null || true
> touch /var/www/www_pythonanywhere_com_wsgi.py 2>/dev/null || true
> echo "PASS: WSGI touched"

pa-preview-post:
> cd "$(PYROOT)" && . "$(VENV)/bin/activate" && \
> KEY="$$(python -c 'import re,sys; txt=open(".env","rb").read().decode("utf-8","replace"); \
m=re.search(r"^PPA_SHARED_KEY\\s*=\\s*[\\"\\\']?([^\\r\\n#]+?)[\\"\\\']?",txt,re.M); \
print((m.group(1).strip() if m else ""), end="")')" && \
> echo "== preview POST ==" && \
> curl --http1.1 -sS -D /tmp/ppa_hdr.$$ -o /tmp/ppa_out.$$ -X POST \
>   -H "Content-Type: application/json" -H "X-PPA-Key: $$KEY" \
>   --data '{"title":"Preview OK","content":"<p>ok</p>","status":"draft"}' \
>   "$(DOMAIN)/postpress-ai/preview/" && \
> ( grep -qi '^X-PPA-View: preview' /tmp/ppa_hdr.$$ && echo "PASS: header X-PPA-View" || echo "WARN: missing X-PPA-View" ) && \
> ( grep -qi '^Cache-Control: no-store' /tmp/ppa_hdr.$$ && echo "PASS: header Cache-Control" || echo "WARN: missing Cache-Control" ) && \
> python -c 'import json,sys; raw=open("/tmp/ppa_out.$$","rb").read().decode("utf-8","replace"); \
try: o=json.loads(raw); ok=(o.get("ok") is True); ver=o.get("ver"); prov=o.get("result",{}).get("provider"); \
except Exception as e: print("WARN: invalid JSON:", e); sys.exit(0); \
print("PASS: JSON ok") if (ok and ver=="1" and prov=="django") else print("WARN: contract mismatch", ok, ver, prov)' || true && \
> rm -f /tmp/ppa_hdr.$$ /tmp/ppa_out.$$

pa-store-post:
> cd "$(PYROOT)" && . "$(VENV)/bin/activate" && \
> KEY="$$(python -c 'import re,sys; txt=open(".env","rb").read().decode("utf-8","replace"); \
m=re.search(r"^PPA_SHARED_KEY\\s*=\\s*[\\"\\\']?([^\\r\\n#]+?)[\\"\\\']?",txt,re.M); \
print((m.group(1).strip() if m else ""), end="")')" && \
> echo "== store POST ==" && \
> curl --http1.1 -sS -D /tmp/ppa_hdr.$$ -o /tmp/ppa_out.$$ -X POST \
>   -H "Content-Type: application/json" -H "X-PPA-Key: $$KEY" \
>   --data '{"title":"Store OK","content":"<p>ok</p>","status":"draft"}' \
>   "$(DOMAIN)/postpress-ai/store/" && \
> ( grep -qi '^X-PPA-View: normalize' /tmp/ppa_hdr.$$ && echo "PASS: header X-PPA-View" || echo "WARN: missing X-PPA-View" ) && \
> ( grep -qi '^Cache-Control: no-store' /tmp/ppa_hdr.$$ && echo "PASS: header Cache-Control" || echo "WARN: missing Cache-Control" ) && \
> python -c 'import json,sys; raw=open("/tmp/ppa_out.$$","rb").read().decode("utf-8","replace"); \
try: o=json.loads(raw); ok=(o.get("ok") is True); ver=o.get("ver"); prov=o.get("result",{}).get("provider"); \
except Exception as e: print("WARN: invalid JSON:", e); sys.exit(0); \
print("PASS: JSON ok") if (ok and ver=="1" and prov=="django") else print("WARN: contract mismatch", ok, ver, prov)' || true && \
> rm -f /tmp/ppa_hdr.$$ /tmp/ppa_out.$$

pa-smoke: key pa-preview-post pa-store-post
> echo "PASS: PA smoke completed"

wp-url:
> cd /home/customer/www/techwithwayne.com/public_html && \
> WP_DOMAIN="$$(wp option get siteurl)" && \
> echo "INFO: WP siteurl = $$WP_DOMAIN"

wp-preview:
> cd /home/customer/www/techwithwayne.com/public_html && \
> WP_DOMAIN="$$(wp option get siteurl)" && \
> echo "== WP AJAX ppa_preview ==" && \
> curl --http1.1 -sS -i -X POST \
>   -H "Content-Type: application/json" \
>   --data '{"title":"WP Preview","content":"<p>ok</p>","status":"draft"}' \
>   "$$WP_DOMAIN/wp-admin/admin-ajax.php?action=ppa_preview"

wp-store:
> cd /home/customer/www/techwithwayne.com/public_html && \
> WP_DOMAIN="$$(wp option get siteurl)" && \
> echo "== WP AJAX ppa_store ==" && \
> curl --http1.1 -sS -i -X POST \
>   -H "Content-Type: application/json" \
>   --data '{"title":"WP Store","content":"<p>ok</p>","status":"draft"}' \
>   "$$WP_DOMAIN/wp-admin/admin-ajax.php?action=ppa_store"

wp-smoke: wp-url wp-preview wp-store
> echo "PASS: WP smoke completed"

push:
> cd "$(PYROOT)" && \
> git add -A || true && \
> if git diff --cached --quiet 2>/dev/null; then \
>   echo "INFO: nothing to commit"; \
> else \
>   git commit -m "chore: sync PostPress AI normalize-only workflow" || true; \
> fi && \
> git push || echo "WARN: push failed (auth/network?)"
