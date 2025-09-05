import re, sys, pathlib

p = pathlib.Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

changed = False

# -------- A) Insert MERGE + TITLE FALLBACK after the existing fields-init block --------
anchor_re = re.compile(
    r'(?ms)(^\s*fields\s*=\s*data\.get\([\'"]fields[\'"]\)\s*or\s*\{\}\s*$\s*^\s*if\s+not\s+isinstance\(\s*fields\s*,\s*dict\s*\)\s*:\s*$\s*^\s*fields\s*=\s*\{\}\s*$)',
    re.M
)

merge_block = r"""
    # [PPA] Merge WP form-encoded fields[...] into JSON `fields` and set title fallback   # CHANGED:
    if request.method == "POST" and getattr(request, "POST", None):                      # CHANGED:
        import re                                                                         # CHANGED:
        skip = {"action", "nonce"}                                                        # CHANGED:
        for _k, _v in request.POST.items():                                              # CHANGED:
            if _k in skip:                                                                # CHANGED:
                continue                                                                  # CHANGED:
            _m = re.match(r"^fields\[(?P<name>[^\]]+)\]$", _k)                           # CHANGED:
            if _m:                                                                        # CHANGED:
                _name = _m.group("name").strip()                                          # CHANGED:
                if _name and _name not in skip:                                           # CHANGED:
                    fields[_name] = _v                                                    # CHANGED:

    # Title fallback                                                                      # CHANGED:
    title = (fields.get("title") or fields.get("subject") or fields.get("headline") or "").strip()  # CHANGED:
    if title and "title" not in fields:                                                   # CHANGED:
        fields["title"] = title                                                           # CHANGED:
"""

def _inject_merge(m):
    return m.group(1) + merge_block

s2, n = anchor_re.subn(_inject_merge, s, count=1)
if n == 1:
    s = s2
    changed = True
else:
    print("ERROR: couldn't find the exact fields-init anchor. Aborting to avoid risky edits.", file=sys.stderr)
    sys.exit(2)

# -------- B) Wrap the final return JsonResponse(...) to add headers + temporary <h1> ----
# We target a single-line 'return JsonResponse(...)'. If your function returns on
# multiple lines, adjust as needed (but most common code is single-line here).
ret_re = re.compile(r'^\s*return\s+JsonResponse\((?P<inside>.+?)\)\s*$', re.M)

inject_before = r"""
    # [PPA] Temporary unblock: ensure title appears in provider HTML if missing           # CHANGED:
    try:                                                                                  # CHANGED:
        _r = result                                                                       # CHANGED:
    except Exception:                                                                      # CHANGED:
        _r = None                                                                          # CHANGED:
    if isinstance(_r, dict):                                                               # CHANGED:
        from django.utils.html import escape                                               # CHANGED:
        _html = _r.get("html") or ""                                                       # CHANGED:
        if 'title' in fields:                                                              # CHANGED:
            _t = (fields.get("title") or "").strip()                                       # CHANGED:
        else:                                                                              # CHANGED:
            _t = (globals().get("title") or locals().get("title") or "").strip()          # CHANGED:
        if _t and (_t.lower() not in _html.lower()):                                       # CHANGED:
            _html = f"<h1>{escape(_t)}</h1>\n{_html}\n<!-- ppa: injected-title -->"       # CHANGED:
            _r["html"] = _html                                                             # CHANGED:
"""

def _wrap_return(m):
    inside = m.group("inside")
    return (
        inject_before +
        f"    resp = JsonResponse({inside})  # CHANGED:\n"
        f"    _t = (locals().get('title') or (fields.get('title') if isinstance(fields, dict) else '') or '').strip()  # CHANGED:\n"
        f"    if _t:\n"
        f"        resp['X-PPA-Parsed-Title'] = _t  # CHANGED:\n"
        f"    try:\n"
        f"        resp['X-PPA-Parsed-Keys'] = ','.join(sorted(fields.keys()))  # CHANGED:\n"
        f"    except Exception:\n"
        f"        resp['X-PPA-Parsed-Keys'] = ''  # CHANGED:\n"
        f"    return resp  # CHANGED:\n"
    )

s2, n = ret_re.subn(_wrap_return, s, count=1)
if n == 1:
    s = s2
    changed = True
else:
    print("ERROR: couldn't find a single-line 'return JsonResponse(...)' to wrap; no header/injection added.", file=sys.stderr)
    # We still wrote the merge block, which unblocks title usage. Exit 0 so the file is saved.
    # If you want strict behavior, change to sys.exit(3)

if changed:
    p.write_text(s, encoding="utf-8")
    print("OK: preview() patched.")
