from __future__ import annotations
from pathlib import Path

def must_utf8(path: Path) -> None:
    path.read_text(encoding="utf-8")


def main() -> int:
    targets: list[Path] = []
    targets += list(Path("gateway/app/templates").rglob("*.html"))
    targets += list(Path("gateway/app/static").rglob("i18n*"))
    targets += list(Path("gateway/app/static/js").rglob("i18n*"))

    bad: list[tuple[str, str]] = []
    for p in targets:
        if not p.is_file():
            continue
        try:
            must_utf8(p)
        except Exception as e:
            bad.append((str(p), str(e)))

    if bad:
        print("UTF8_CHECK_FAILED:", len(bad))
        for p, e in bad[:120]:
            print(" -", p, "=>", e)
        return 2

    print("UTF8_CHECK_OK:", len(targets), "files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
