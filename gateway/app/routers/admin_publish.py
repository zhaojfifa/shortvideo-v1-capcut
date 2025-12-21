from __future__ import annotations

from fastapi import APIRouter
from gateway.app.deps import get_task_repository
from gateway.app.services.publish_service import publish_task_pack

router = APIRouter()


@router.post("/api/admin/publish/backfill")
def backfill(limit: int = 50, provider: str | None = None, force: bool = False):
    repo = get_task_repository()
    tasks = [
        task
        for task in repo.list()
        if task.get("pack_path")
        and (task.get("publish_key") is None or task.get("publish_key") == "")
    ]
    tasks = tasks[:limit]
    out = []
    for task in tasks:
        task_id = task.get("task_id") or task.get("id")
        try:
            res = publish_task_pack(task_id, repo, provider=provider, force=force)
            out.append(
                {
                    "task_id": task_id,
                    "ok": True,
                    "provider": res["provider"],
                    "key": res["publish_key"],
                }
            )
        except Exception as exc:
            repo.update(task_id, {"publish_status": "error"})
            out.append({"task_id": task_id, "ok": False, "error": str(exc)})
    return {"count": len(out), "results": out}
