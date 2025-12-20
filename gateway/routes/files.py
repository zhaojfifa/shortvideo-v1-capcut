import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from gateway.app.config import get_settings

router = APIRouter()

ALLOWED_TOP_DIRS = {"raw", "tasks", "audio", "pack"}


def _workspace_root() -> Path:
    settings = get_settings()
    return Path(settings.workspace_root).resolve()


@router.get("/files/{rel_path:path}")
def serve_workspace_file(rel_path: str):
    rel_path = (rel_path or "").lstrip("/")
    if not rel_path:
        raise HTTPException(status_code=404, detail="Not Found")

    top = rel_path.split("/", 1)[0]
    if top not in ALLOWED_TOP_DIRS:
        raise HTTPException(status_code=404, detail="Not Found")

    root = _workspace_root()
    file_path = (root / rel_path).resolve()
    if not str(file_path).startswith(str(root) + os.sep):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(str(file_path))
