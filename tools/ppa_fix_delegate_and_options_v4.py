import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

# --- locate preview() function block ---
m = re.search(r'(?m)^def\s+preview\s*\(.*?\):', src)
if not m:
    print("ERROR: preview() not found; no changes made.", file=sys.stderr); sys.exit(2)

sig_end = src.find("\n", m.end()) + 1
after = src[sig_end:]
indent_match = re.match(r'([ \t]+)', after)
base_indent = indent_match.group(1) if indent_match else "    "

m_end = re.search(r'(?m)^(def|class)\s+\w+\s*\(', src[sig_end:])
func_end = sig_end + (m_end.start() if m_end else len(src[sig_end:]))

func = src[m.start():func_end]

# --- A) Fix OPTIONS branch: avoid local _with_cors scoping issue ---
# Replace: return _with_cors(HttpResponse(status=204), request)
# With:    safe module lookup to avoid UnboundLocalError
opt_pat = re.compile(
    r'(?ms)^%sif\s+request\.method\s*==\s*[\'"]OPTIONS[\'"]\s*:\s*\n%sreturn\s+_with_cors\(\s*HttpResponse\(\s*status\s*=\s*204\s*\)\s*,\s*request\s*\)\s*$'
    % (re.escape(base_indent), re.escape(base_indent))
)
def _opt_repl(mo):
    return (
f"""{base_indent}if request.method == "OPTIONS":
{base_indent}    resp = HttpResponse(status=204)
{base_indent}    import sys
{base_indent}    _cors = getattr(sys.modules[__name__], "_with_cors", None)
{base_indent}    if callable(_cors):
{base_indent}        return _cors(resp, request)
{base_indent}    return resp"""
)
func_new, n1 = opt_pat.subn(_opt_repl, func, count=1)
if n1 == 0:
    # Not fatal; carry on (maybe already fixed or shaped differently)
    func_new = func

# --- B) Wrap LAST return JsonResponse(...) to inject top-level ver and keep prior normalizations ---
ret_iter = list(re.finditer(r'(?m)^\s*return\s+JsonResponse\((?P<inside>.+?)\)\s*$', func_new))
if not ret_iter:
    print("ERROR: couldn't find a single-line 'return JsonResponse(...)' in preview(); no changes made.", file=sys.stderr)
    sys.exit(4)

last = ret_iter[-1]
inside = last.group('inside')

wrap = f"""
{base_indent}# [PPA] Finalize response: ensure delegate contract + top-level ver              # CHANGED:
{base_indent}import json, sys                                                                  # CHANGED:
{base_indent}# (Assumes earlier blocks normalized `result` and provider comment as needed.)    # CHANGED:
{base_indent}resp = JsonResponse({inside})  # preserve original payload                        # CHANGED:
{base_indent}# Inject top-level 'ver' without losing any other keys                            # CHANGED:
{base_indent}try:                                                                              # CHANGED:
{base_indent}    _payload = json.loads(resp.content.decode("utf-8"))                           # CHANGED:
{base_indent}    if isinstance(_payload, dict) and "ver" not in _payload:                      # CHANGED:
{base_indent}        _payload["ver"] = "1"                                                     # CHANGED:
{base_indent}        resp.content = json.dumps(_payload).encode("utf-8")                       # CHANGED:
{base_indent}except Exception:                                                                 # CHANGED:
{base_indent}    pass                                                                           # CHANGED:
{base_indent}# Debug headers                                                                   # CHANGED:
{base_indent}_title = (locals().get("title") or (fields.get("title") if isinstance(locals().get("fields"), dict) else "") or "").strip()  # CHANGED:
{base_indent}if _title:                                                                        # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Title"] = _title                                           # CHANGED:
{base_indent}try:                                                                              # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Keys"] = ",".join(sorted(fields.keys()))                   # CHANGED:
{base_indent}except Exception:                                                                 # CHANGED:
{base_indent}    resp["X-PPA-Parsed-Keys"] = ""                                                # CHANGED:
{base_indent}return resp                                                                       # CHANGED:
""".rstrip("\n")

func_new = func_new[:last.start()] + wrap + func_new[last.end():]

# --- write back ---
new_src = src[:m.start()] + func_new + src[func_end:]
p.write_text(new_src, encoding="utf-8")
print("OK: preview() patched: OPTIONS safe + top-level ver injection.")
