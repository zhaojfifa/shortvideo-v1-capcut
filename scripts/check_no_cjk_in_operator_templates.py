#!/usr/bin/env python3
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "gateway" / "app" / "templates"

CJK = re.compile(r"[\u4e00-\u9fff]")

ALLOWLIST = set(
    [
        # If any legacy files must be kept, list them here.
    ]
)


def main() -> int:
    bad = []
    for p in sorted(TPL_DIR.glob("*.html")):
        if p.name in ALLOWLIST:
            continue
        try:
            s = p.read_text(encoding="utf-8")
        except Exception as e:
            bad.append((str(p), f"NOT_UTF8: {e}"))
            continue
        if CJK.search(s):
            bad.append((str(p), "HAS_CJK"))
    if bad:
        print("Operator templates check failed:")
        for f, why in bad:
            print(f" - {f}: {why}")
        return 1
    print("OK: no CJK and all templates are UTF-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
