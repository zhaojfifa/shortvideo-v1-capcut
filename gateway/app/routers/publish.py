from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from gateway.app import schemas
from gateway.app.deps import get_task_repository
from gateway.app.services.publish_service import publish_task_pack, resolve_download_url

router = APIRouter()


@router.post("/v1/publish", response_model=schemas.PublishResponse)
def publish(req: schemas.PublishRequest, repo=Depends(get_task_repository)):
    try:
        res = publish_task_pack(req.task_id, repo, provider=req.provider, force=req.force)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = repo.get(req.task_id)
    download_url = resolve_download_url(task) if task else ""

    return schemas.PublishResponse(
        task_id=req.task_id,
        provider=res["provider"],
        publish_key=res["publish_key"],
        download_url=download_url,
        published_at=res["published_at"],
    )


@router.get("/v1/tasks/{task_id}/pack")
def download_pack(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    url = resolve_download_url(task)
    if not url:
        raise HTTPException(status_code=404, detail="Pack not found")

    return RedirectResponse(url=url, status_code=302)
