from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.app.core.pack_v17_youcut import generate_youcut_pack


def _zip_pack(pack_root: Path, zip_path: Path) -> None:
    with ZipFile(zip_path, "w") as zf:
        for path in pack_root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(pack_root)
                zf.write(path, arcname=f"{pack_root.name}/{rel.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v1.7 YouCut pack skeleton.")
    parser.add_argument("--task_id", required=True)
    parser.add_argument("--out", default="deliver/packs")
    parser.add_argument("--zip", dest="zip", action="store_true", default=True)
    parser.add_argument("--no-zip", dest="zip", action="store_false")
    args = parser.parse_args()

    out_root = Path(args.out)
    pack_root = generate_youcut_pack(args.task_id, out_root, placeholders=True)
    zip_path = out_root / f"{args.task_id}.zip"

    if args.zip:
        _zip_pack(pack_root, zip_path)

    print(f"pack: {pack_root}")
    if args.zip:
        print(f"zip: {zip_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
