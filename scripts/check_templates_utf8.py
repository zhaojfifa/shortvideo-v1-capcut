from pathlib import Path
import sys

bad = []
root = Path("gateway/app/templates")
for p in root.rglob("*.html"):
    b = p.read_bytes()
    try:
        b.decode("utf-8")
    except UnicodeDecodeError as e:
        bad.append((p, e))

if bad:
    print("[FAIL] Non-UTF8 templates found:")
    for p,e in bad:
        print(f" - {p}: {e}")
    sys.exit(1)

print("[OK] All templates are UTF-8:", root)
