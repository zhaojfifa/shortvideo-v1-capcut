from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path("gateway/app/templates")
    bad = []
    for p in root.rglob("*.html"):
        try:
            p.read_text(encoding="utf-8")
        except Exception as e:
            bad.append((str(p), str(e)))

    if bad:
        print("Non-UTF8 templates found:")
        for p, e in bad:
            print(" -", p, "->", e)
        return 2

    print("OK: all templates are UTF-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
