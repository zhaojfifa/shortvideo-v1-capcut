from pathlib import Path
import re
import sys

root = Path("gateway/app/templates")
cjk = re.compile(r"[\u4e00-\u9fff]")

hits = []
for p in root.rglob("*.html"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if cjk.search(line):
            hits.append((p, i, line.strip()))

if hits:
    print("[FAIL] CJK found in templates:")
    for p, i, line in hits:
        print(f" - {p}:{i}: {line}")
    sys.exit(1)

print("[OK] No CJK found in templates.")
