import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

# Find the preview() definition block
m = re.search(r'(?m)^def\s+preview\s*\(.*?\):', src)
if not m:
    print("ERROR: preview() not found; no changes made.", file=sys.stderr); sys.exit(2)

sig_end = src.find("\n", m.end()) + 1
body_after_sig = src[sig_end:]
indent_match = re.match(r'([ \t]+)', body_after_sig)
base_indent = indent_match.group(1) if indent_match else "    "

# Boundaries of function (until next top-level def/class or EOF)
m_end = re.search(r'(?m)^(def|class)\s+\w+\s*\(', src[sig_end:])
func_end = sig_end + (m_end.start() if m_end else len(src[sig_end:]))

func_block = src[m.start():func_end]

# Find the LAST single-line return JsonResponse(...) inside preview()
rets = list(re.finditer(r'(?m)^\s*return\s+JsonResponse\((?P<inside>.+?)\)\s*$', func_block))
if not rets:
    print("ERROR: couldn't find a single-line 'return JsonResponse(...)' in preview(); no changes made.", file=sys.stderr)
    sys.exit(4)

last = rets[-1]
inside = last.group('inside')

# Build wrapper that:
# - Rebuilds fields if needed (JSON + form merge)
# - Computes title fallback
# - Supports forced fallback flag (GET or fields)
# - Validates/repairs delegate result contract; adds 'ver'
# - Injects provider comment: 'delegate', 'local-fallback', or 'forced'
# - Ensures title appears in HTML
# - Adds debug headers
wrap = f"""
{base_indent}# [PPA] Delegate contract enforcement + fallbacks (test fixes)                 # CHANGED:
{base_indent}import json, re                                                                 # CHANGED:
{base_indent}from django.utils.html import escape                                            # CHANGED:
{base_indent}
{base_indent}# Best-effort recover/merge fields (if not already present)                     # CHANGED:
{base_indent}try:                                                                            # CHANGED:
{base_indent}    _data = json.loads((request.body or b"").decode("utf-8") or "{{}}")        # CHANGED:
{base_indent}except Exception:                                                               # CHANGED:
{base_indent}    _data = {{}}                                                                # CHANGED:
{base_indent}_fields = dict(_data.get("fields") or {{}}) if isinstance(_data.get("fields"), dict) else dict()  # CHANGED:
{base_indent}if getattr(request, "method", "GET") == "POST" and getattr(request, "POST", None):  # CHANGED:
{base_indent}    _skip = {{"action", "nonce"}}                                               # CHANGED:
{base_indent}    for _k, _v in request.POST.items():                                         # CHANGED:
{base_indent}        if _k in _skip:                                                         # CHANGED:
{base_indent}            continue                                                            # CHANGED:
{base_indent}        _m = re.match(r"^fields\\[(?P<name>[^\\]]+)\\]$", _k)                   # CHANGED:
{base_indent}        if _m:                                                                  # CHANGED:
{base_indent}            _name = _m.group("name").strip()                                    # CHANGED:
{base_indent}            if _name and _name not in _skip:                                    # CHANGED:
{base_indent}                _fields[_name] = _v                                             # CHANGED:
{base_indent}
{base_indent}# Prefer existing locals() values if present                                    # CHANGED:
{base_indent}fields = locals().get("fields") if isinstance(locals().get("fields"), dict) else _fields  # CHANGED:
{base_indent}title = (locals().get("title") or fields.get("title") or fields.get("subject") or fields.get("headline") or "").strip()  # CHANGED:
{base_indent}if title and "title" not in fields:                                             # CHANGED:
{base_indent}    fields["title"] = title                                                     # CHANGED:
{base_indent}
{base_indent}def _truthy(x):                                                                 # CHANGED:
{base_indent}    return str(x).lower() in ("1","true","yes","y","on")                        # CHANGED:
{base_indent}
{base_indent}_forced = _truthy(request.GET.get("force_fallback")) or _truthy(fields.get("force_fallback"))  # CHANGED:
{base_indent}
{base_indent}def _fallback(_tag):                                                            # CHANGED:
{base_indent}    _h = ""                                                                     # CHANGED:
{base_indent}    if title:                                                                   # CHANGED:
{base_indent}        _h = f"<h1>{{escape(title)}}</h1>\\n"                                   # CHANGED:
{base_indent}    _h += "<p>Preview is using a local fallback.</p>"                           # CHANGED:
{base_indent}    _h += f"\\n<!-- provider: {{_tag}} -->"                                     # CHANGED:
{base_indent}    return {{"title": title, "html": _h, "ver": "1"}}                           # CHANGED:
{base_indent}
{base_indent}# Try to read current 'result' and repair/replace as needed                     # CHANGED:
{base_indent}try:                                                                            # CHANGED:
{base_indent}    _r = result                                                                 # CHANGED:
{base_indent}except Exception:                                                               # CHANGED:
{base_indent}    _r = None                                                                   # CHANGED:
{base_indent}
{base_indent}if _forced:                                                                     # CHANGED:
{base_indent}    _r = _fallback("forced")                                                    # CHANGED:
{base_indent}else:                                                                           # CHANGED:
{base_indent}    # If delegate returned malformed/non-JSON, switch to local fallback         # CHANGED:
{base_indent}    if not (isinstance(_r, dict) and isinstance(_r.get("html"), str)):         # CHANGED:
{base_indent}        _r = _fallback("local-fallback")                                        # CHANGED:
{base_indent}    else:                                                                       # CHANGED:
{base_indent}        # Valid delegate: ensure ver and provider comment                       # CHANGED:
{base_indent}        if "ver" not in _r:                                                     # CHANGED:
{base_indent}            _r["ver"] = "1"                                                     # CHANGED:
{base_indent}        _html = _r.get("html") or ""                                            # CHANGED:
{base_indent}        if "<!-- provider:" not in _html:                                       # CHANGED:
{base_indent}            _html = _html + "\\n<!-- provider: delegate -->"                    # CHANGED:
{base_indent}            _r["html"] = _html                                                  # CHANGED:
{base_indent}
{base_indent}# Ensure visible title if missing in HTML                                       # CHANGED:
{base_indent}if title and isinstance(_r, dict):                                              # CHANGED:
{base_indent}    _html = _r.get("html") or ""                                                # CHANGED:
{base_indent}    if title.lower() not in _html.lower():                                      # CHANGED:
{base_indent}        _r["html"] = f"<h1>{{escape(title)}}</h1>\\n{{_html}}"                  # CHANGED:
{base_indent}
{base_indent}# Replace the 'result' going into the response                                  # CHANGED:
{base_indent}result = _r                                                                     # CHANGED:
{base_indent}
{base_indent}resp = JsonResponse({inside})  # CHANGED: use the original payload expression   # CHANGED:
{base_indent}if title:                                                                       # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Title"] = title                                          # CHANGED:
{base_indent}try:                                                                            # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Keys"] = ",".join(sorted(fields.keys()))                 # CHANGED:
{base_indent}except Exception:                                                               # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Keys"] = ""                                              # CHANGED:
{base_indent}return resp                                                                     # CHANGED:
"""

# Splice the wrapper into the function
func_block_new = func_block[:last.start()] + wrap + func_block[last.end():]
new_src = src[:m.start()] + func_block_new + src[func_end:]
p.write_text(new_src, encoding="utf-8")
print("OK: preview() wrapped safely (contract enforcement + fallbacks).")
