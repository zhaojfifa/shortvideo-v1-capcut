from __future__ import annotations

import uuid
from starlette.datastructures import UploadFile

from gateway.app.services.artifact_storage import upload_task_artifact, get_download_url


def _ext(name: str, fallback: str) -> str:
    if "." in name:
        return name.rsplit(".", 1)[-1].lower()
    return fallback


async def save_avatar_image(task: dict, file: UploadFile) -> str:
    data = await file.read()
    suffix = _ext(file.filename or "", "jpg")
    key_name = f"apollo_avatar/avatar_{uuid.uuid4().hex}.{suffix}"
    path = file.file
    # write to a temp file path using upload_task_artifact
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    upload_task_artifact(task, tmp_path, key_name)
    return get_download_url(task.get("task_id") or task.get("id"), key_name)


async def save_ref_video(task: dict, file: UploadFile) -> str:
    data = await file.read()
    suffix = _ext(file.filename or "", "mp4")
    key_name = f"apollo_avatar/ref_{uuid.uuid4().hex}.{suffix}"
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    upload_task_artifact(task, tmp_path, key_name)
    return get_download_url(task.get("task_id") or task.get("id"), key_name)
