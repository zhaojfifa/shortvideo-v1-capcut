from pathlib import Path

root = Path(__file__).resolve().parents[1] / "templates"
bad = []

for p in root.rglob("*.html"):
    b = p.read_bytes()
    try:
        b.decode("utf-8")
    except UnicodeDecodeError as e:
        bad.append((str(p), str(e)))

if bad:
    print("Non-UTF8 templates found:")
    for p, e in bad:
        print(" -", p, "->", e)
    raise SystemExit(2)

print("OK: all templates are UTF-8")
