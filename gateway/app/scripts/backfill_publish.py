from __future__ import annotations

import argparse

from gateway.app.deps import get_task_repository
from gateway.app.services.publish_service import publish_task_pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--provider", type=str, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    repo = get_task_repository()
    tasks = [
        task
        for task in repo.list()
        if task.get("pack_path")
        and (task.get("publish_key") is None or task.get("publish_key") == "")
    ]
    tasks = tasks[: args.limit]
    print(f"Backfill tasks: {len(tasks)}")

    for task in tasks:
        task_id = task.get("task_id") or task.get("id")
        try:
            res = publish_task_pack(
                task_id,
                repo,
                provider=args.provider,
                force=args.force,
            )
            print(
                f"[OK] {task_id} provider={res['provider']} key={res['publish_key']}"
            )
        except Exception as exc:
            repo.update(task_id, {"publish_status": "error"})
            print(f"[ERR] {task_id} {exc}")


if __name__ == "__main__":
    main()
