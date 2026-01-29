#!/usr/bin/env python3
import re
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]")

ROOTS = [
    Path("gateway/app/templates"),
    Path("gateway/app/static/js"),
]

ALLOWLIST = {
    # If there are unavoidable exceptions, list them here.
}


def main() -> int:
    bad = []
    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".html", ".js"}:
                continue
            rel = str(p)
            if rel in ALLOWLIST:
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(txt.splitlines(), 1):
                if CJK.search(line):
                    bad.append((rel, i, line.strip()))
    if bad:
        print("Found CJK in operator templates/assets:")
        for rel, i, line in bad[:200]:
            print(f"- {rel}:{i}: {line}")
        print(f"Total hits: {len(bad)}")
        return 1
    print("OK: no CJK found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
