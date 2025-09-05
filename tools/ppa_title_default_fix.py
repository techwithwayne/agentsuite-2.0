import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

pattern = re.compile(
    r'(\btitle\s*=\s*\(fields\.get\("title"\)\s*\|\|\s*fields\.get\("subject"\)\s*\|\|\s*fields\.get\("headline"\)\s*\|\|\s*""\)\.strip\(\)\s*\n)'
    r'(\s*if\s+title\s+and\s+"title"\s+not\s+in\s+fields:\s*\n\s*fields\["title"\]\s*=\s*title\s*)',
    re.M
)

# more flexible matcher for typical formatting
flex = re.compile(
    r'(?ms)'
    r'(?P<assign>^\s*title\s*=\s*\(fields\.get\([\'"]title[\'"]\)\s*'
    r'\|\|\s*fields\.get\([\'"]subject[\'"]\)\s*'
    r'\|\|\s*fields\.get\([\'"]headline[\'"]\)\s*'
    r'\|\|\s*""\)\.strip\(\)\s*$)'
    r'(?P<after>\s*^\s*if\s+title\s+and\s+"title"\s+not\s+in\s+fields:\s*$\s*^\s*fields\["title"\]\s*=\s*title\s*$)'
)

if pattern.search(s):
    s = pattern.sub(
        r'\1'
        r'    if not title:\n'
        r'        title = "Preview"\n'
        r'    if "title" not in fields:\n'
        r'        fields["title"] = title\n',
        s, count=1
    )
else:
    m = flex.search(s)
    if not m:
        print("ERROR: Could not find title-fallback anchor; no changes made.", file=sys.stderr)
        sys.exit(2)
    start, end = m.span()
    block = m.group(0)
    lines = []
    for line in block.splitlines(True):
        lines.append(line)
    # replace the block with default logic
    new_block = (
        f"{m.group('assign')}\n"
        f"    if not title:\n"
        f'        title = "Preview"\n'
        f'    if "title" not in fields:\n'
        f'        fields["title"] = title\n'
    )
    s = s[:start] + new_block + s[end:]

p.write_text(s, encoding="utf-8")
print("OK: title default injected (Preview).")
