import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

# find preview() block boundaries
m = re.search(r'(?m)^def\s+preview\s*\(.*?\):', src)
if not m:
    print("ERROR: preview() not found; no changes made.", file=sys.stderr); sys.exit(2)
sig_end = src.find("\n", m.end()) + 1
body_after = src[sig_end:]
indent_match = re.match(r'([ \t]+)', body_after)
base_indent = indent_match.group(1) if indent_match else "    "
m_end = re.search(r'(?m)^(def|class)\s+\w+\s*\(', src[sig_end:])
func_end = sig_end + (m_end.start() if m_end else len(src[sig_end:]))
func = src[m.start():func_end]

changed = False

# --- A) Fix OPTIONS one-liner: "if ...: return _with_cors(HttpResponse(status=204), request)"
one_liner = re.compile(
    r'(?m)^(?P<i>[ \t]*)if\s*request\.method\s*==\s*["\']OPTIONS["\']\s*:\s*return\s*_with_cors\(\s*HttpResponse\(\s*status\s*=\s*204\s*\)\s*,\s*request\s*\)\s*$'
)
def repl_one(mo):
    i = mo.group('i')
    return (
f"""{i}if request.method == "OPTIONS":
{i}    resp = HttpResponse(status=204)
{i}    import sys
{i}    _cors = getattr(sys.modules[__name__], "_with_cors", None)
{i}    if callable(_cors):
{i}        return _cors(resp, request)
{i}    return resp"""
)
func2, n1 = one_liner.subn(repl_one, func)
if n1:
    func = func2
    changed = True

# --- B) Fix OPTIONS two-liner: inside block "return _with_cors(HttpResponse(...), request)"
two_liner = re.compile(
    r'(?m)^(?P<i>[ \t]*)if\s*request\.method\s*==\s*["\']OPTIONS["\']\s*:\s*\n(?P<r>[ \t]*)return\s*_with_cors\(\s*HttpResponse\(\s*status\s*=\s*204\s*\)\s*,\s*request\s*\)\s*$'
)
def repl_two(mo):
    i = mo.group('i')
    r = mo.group('r')  # inner indent (usually i + 4)
    return (
f"""{i}if request.method == "OPTIONS":
{r}resp = HttpResponse(status=204)
{r}import sys
{r}_cors = getattr(sys.modules[__name__], "_with_cors", None)
{r}if callable(_cors):
{r}    return _cors(resp, request)
{r}return resp"""
)
func2, n2 = two_liner.subn(repl_two, func)
if n2:
    func = func2
    changed = True

# --- C) Wrap ALL single-line 'return JsonResponse(...)' to inject top-level ver + headers
ret_re = re.compile(r'(?m)^(?P<i>[ \t]*)return\s+JsonResponse\((?P<inside>.+?)\)\s*$')
def wrap_return(mo):
    i = mo.group('i')
    inside = mo.group('inside')
    return (
f"""{i}# [PPA] normalize payload + inject top-level ver                                     # CHANGED:
{i}_payload = {inside}
{i}try:
{i}    # Add top-level ver if missing
{i}    if isinstance(_payload, dict) and "ver" not in _payload:
{i}        _payload["ver"] = "1"
{i}except Exception:
{i}    pass
{i}resp = JsonResponse(_payload)  # preserve original structure                             # CHANGED:
{i}# Debug headers                                                                           # CHANGED:
{i}_title = (locals().get("title") or (fields.get("title") if isinstance(locals().get("fields"), dict) else "") or "").strip()
{i}if _title:
{i}    resp["X-PPA-Parsed-Title"] = _title
{i}try:
{i}    resp["X-PPA-Parsed-Keys"] = ",".join(sorted(fields.keys()))
{i}except Exception:
{i}    resp["X-PPA-Parsed-Keys"] = ""
{i}return resp"""
)
func2, n3 = ret_re.subn(wrap_return, func)
if n3:
    func = func2
    changed = True

if not changed:
    print("ERROR: No changes applied (anchors not found).", file=sys.stderr); sys.exit(3)

new_src = src[:m.start()] + func + src[func_end:]
p.write_text(new_src, encoding="utf-8")
print(f"OK: patched preview(): OPTIONS safe ({n1+n2} sites) + wrapped {n3} JsonResponse returns.")
