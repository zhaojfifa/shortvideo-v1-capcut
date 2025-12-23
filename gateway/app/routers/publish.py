from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from gateway.app import models, schemas
from gateway.app.db import get_db
from gateway.app.services.artifact_storage import get_download_url, object_exists
from gateway.app.services.publish_service import publish_task_pack, resolve_download_url

router = APIRouter()


@router.post("/v1/publish", response_model=schemas.PublishResponse)
def publish(req: schemas.PublishRequest, db: Session = Depends(get_db)):
    try:
        res = publish_task_pack(req.task_id, db, provider=req.provider, force=req.force)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = db.query(models.Task).filter(models.Task.id == req.task_id).first()
    download_url = resolve_download_url(task) if task else ""

    return schemas.PublishResponse(
        task_id=req.task_id,
        provider=res["provider"],
        publish_key=res["publish_key"],
        download_url=download_url,
        published_at=res["published_at"],
    )


@router.get("/v1/tasks/{task_id}/pack")
def download_pack(task_id: str, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pack not found")
    if not task.pack_path or not object_exists(str(task.pack_path)):
        raise HTTPException(status_code=404, detail="Pack not found")
    url = get_download_url(task.pack_path)
    return RedirectResponse(url=url, status_code=302)
