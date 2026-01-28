from pathlib import Path
import sys

roots = [
    Path("gateway/app/templates"),
]

bad = []
for r in roots:
    if not r.exists():
        continue
    for p in r.rglob("*.html"):
        try:
            p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            bad.append((p, str(e)))

if bad:
    print("Non-UTF8 template files detected:")
    for p, e in bad:
        print(f"- {p}: {e}")
    sys.exit(1)

print("All template .html files are valid UTF-8.")
