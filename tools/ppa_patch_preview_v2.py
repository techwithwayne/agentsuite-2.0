import re, sys, pathlib

p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

# --- find def preview(...) block boundaries (start to next top-level def/class or EOF) ---
m = re.search(r'(?m)^def\s+preview\s*\(.*?\):', src)
if not m:
    print("ERROR: preview() not found; no changes made.", file=sys.stderr)
    sys.exit(2)

func_start = m.start()
# find first non-empty line after signature to detect base indent
sig_end = src.find("\n", m.end()) + 1
body_after_sig = src[sig_end:]
indent_match = re.match(r'([ \t]+)', body_after_sig)
base_indent = indent_match.group(1) if indent_match else "    "

# find function end: next top-level def/class
m_end = re.search(r'(?m)^(def|class)\s+\w+\s*\(', src[sig_end:])
func_end = sig_end + (m_end.start() if m_end else len(src[sig_end:]))

func_block = src[func_start:func_end]

# --- insert MERGE + TITLE FALLBACK after the "fields" init block ---
# Common init pattern: fields = data.get("fields") or {}; if not isinstance(fields, dict): fields = {}
fields_anchor = re.search(
    r'(?ms)(\n%sfields\s*=\s*data\.get\([\'"]fields[\'"]\)\s*or\s*\{\}\s*\n%sif\s+not\s+isinstance\(\s*fields\s*,\s*dict\s*\)\s*:\s*\n%sfields\s*=\s*\{\}\s*\n)'
    % (re.escape(base_indent), re.escape(base_indent), re.escape(base_indent)),
    func_block
)
# Fallback: if exact triple isn't present, try first "fields =" occurrence
if not fields_anchor:
    fields_anchor = re.search(r'(?m)\n%sfields\s*=' % re.escape(base_indent), func_block)

if not fields_anchor:
    print("ERROR: couldn't locate fields-init block; no changes made.", file=sys.stderr)
    sys.exit(3)

merge_block = f"""
{base_indent}# [PPA] Merge WP form-encoded fields[...] into JSON `fields` and set title fallback   # CHANGED:
{base_indent}if getattr(request, "method", "GET") == "POST" and getattr(request, "POST", None):    # CHANGED:
{base_indent}    import re                                                                          # CHANGED:
{base_indent}    skip = {{"action", "nonce"}}                                                       # CHANGED:
{base_indent}    for _k, _v in request.POST.items():                                                # CHANGED:
{base_indent}        if _k in skip:                                                                 # CHANGED:
{base_indent}            continue                                                                   # CHANGED:
{base_indent}        _m = re.match(r"^fields\\[(?P<name>[^\\]]+)\\]$", _k)                          # CHANGED:
{base_indent}        if _m:                                                                         # CHANGED:
{base_indent}            _name = _m.group("name").strip()                                           # CHANGED:
{base_indent}            if _name and _name not in skip:                                            # CHANGED:
{base_indent}                fields[_name] = _v                                                     # CHANGED:
{base_indent}
{base_indent}title = (fields.get("title") or fields.get("subject") or fields.get("headline") or "").strip()  # CHANGED:
{base_indent}if title and "title" not in fields:                                                    # CHANGED:
{base_indent}    fields["title"] = title                                                            # CHANGED:
"""

insert_pos = fields_anchor.end()
func_block = func_block[:insert_pos] + merge_block + func_block[insert_pos:]

# --- wrap the LAST 'return JsonResponse(...)' inside preview() ---
# Find last single-line 'return JsonResponse(...)' within func_block
ret_iter = list(re.finditer(r'(?m)^\s*return\s+JsonResponse\((?P<inside>.+)\)\s*$', func_block))
if ret_iter:
    last = ret_iter[-1]
    inside = last.group('inside')

    # Build the replacement chunk with temp <h1> injection + headers then return resp
    wrap = f"""
{base_indent}# [PPA] Temporary unblock: ensure title appears in provider HTML if missing            # CHANGED:
{base_indent}try:                                                                                   # CHANGED:
{base_indent}    _r = result                                                                        # CHANGED:
{base_indent}except Exception:                                                                       # CHANGED:
{base_indent}    _r = None                                                                           # CHANGED:
{base_indent}if isinstance(_r, dict):                                                                # CHANGED:
{base_indent}    from django.utils.html import escape                                                # CHANGED:
{base_indent}    _html = _r.get("html") or ""                                                        # CHANGED:
{base_indent}    _t = title if 'title' in locals() else (fields.get('title') if isinstance(fields, dict) else "")  # CHANGED:
{base_indent}    _t = (_t or "").strip()                                                             # CHANGED:
{base_indent}    if _t and (_t.lower() not in _html.lower()):                                        # CHANGED:
{base_indent}        _html = f"<h1>{{escape(_t)}}</h1>\\n{{_html}}\\n<!-- ppa: injected-title -->"  # CHANGED:
{base_indent}        _r["html"] = _html                                                              # CHANGED:
{base_indent}
{base_indent}resp = JsonResponse({inside})  # CHANGED:
{base_indent}if (locals().get('title') or (fields.get('title') if isinstance(fields, dict) else '')):  # CHANGED:
{base_indent}    resp['X-PPA-Parsed-Title'] = (locals().get('title') or fields.get('title') or '').strip()  # CHANGED:
{base_indent}try:                                                                                   # CHANGED:
{base_indent}    resp['X-PPA-Parsed-Keys'] = ",".join(sorted(fields.keys()))                        # CHANGED:
{base_indent}except Exception:                                                                      # CHANGED:
{base_indent}    resp['X-PPA-Parsed-Keys'] = ""                                                     # CHANGED:
{base_indent}return resp                                                                            # CHANGED:
""".rstrip("\n")

    func_block = func_block[:last.start()] + wrap + func_block[last.end():]
else:
    print("ERROR: couldn't find a single-line 'return JsonResponse(...)' inside preview(); no changes made.", file=sys.stderr)
    sys.exit(4)

# --- write back (only the function block is replaced) ---
new_src = src[:func_start] + func_block + src[func_end:]
p.write_text(new_src, encoding="utf-8")
print("OK: preview() patched in-place (no top-level prepends).")
