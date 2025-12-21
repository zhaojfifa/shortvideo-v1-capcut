from __future__ import annotations

import argparse

from gateway.app import models
from gateway.app.db import SessionLocal
from gateway.app.services.publish_service import publish_task_pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--provider", type=str, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        tasks = (
            db.query(models.Task)
            .filter(models.Task.pack_path.isnot(None))
            .filter((models.Task.publish_key.is_(None)) | (models.Task.publish_key == ""))
            .order_by(models.Task.created_at.desc())
            .limit(args.limit)
            .all()
        )
        print(f"Backfill tasks: {len(tasks)}")

        for task in tasks:
            try:
                res = publish_task_pack(
                    task.id,
                    db,
                    provider=args.provider,
                    force=args.force,
                )
                print(
                    f"[OK] {task.id} provider={res['provider']} key={res['publish_key']}"
                )
            except Exception as exc:
                task.publish_status = "error"
                db.commit()
                print(f"[ERR] {task.id} {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
