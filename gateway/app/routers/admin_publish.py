from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from gateway.app import models
from gateway.app.db import SessionLocal
from gateway.app.services.publish_service import publish_task_pack

router = APIRouter()


@router.post("/api/admin/publish/backfill")
def backfill(limit: int = 50, provider: str | None = None, force: bool = False):
    db: Session = SessionLocal()
    try:
        tasks = (
            db.query(models.Task)
            .filter(models.Task.pack_path.isnot(None))
            .filter((models.Task.publish_key.is_(None)) | (models.Task.publish_key == ""))
            .order_by(models.Task.created_at.desc())
            .limit(limit)
            .all()
        )
        out = []
        for task in tasks:
            try:
                res = publish_task_pack(task.id, db, task_repo=None, provider=provider, force=force)
                out.append(
                    {
                        "task_id": task.id,
                        "ok": True,
                        "provider": res["provider"],
                        "key": res["publish_key"],
                    }
                )
            except Exception as exc:
                task.publish_status = "error"
                db.commit()
                out.append({"task_id": task.id, "ok": False, "error": str(exc)})
        return {"count": len(out), "results": out}
    finally:
        db.close()
