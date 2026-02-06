from __future__ import annotations

from typing import Optional

from gateway.app.routers import tasks as tasks_router
from gateway.app.services.artifact_storage import get_download_url, object_exists


def _task_value(task: dict, field: str) -> Optional[str]:
    if isinstance(task, dict):
        return task.get(field)
    return getattr(task, field, None)


def _task_key(task: dict, field: str) -> Optional[str]:
    value = _task_value(task, field)
    return str(value) if value else None


def _deliverable_url(task_id: str, task: dict, kind: str) -> Optional[str]:
    if kind == "final_mp4":
        key = _task_key(task, "raw_path")
        return tasks_router._signed_op_url(task_id, "raw") if key and object_exists(key) else None
    if kind == "pack_zip":
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        if pack_key and object_exists(str(pack_key)):
            return tasks_router._signed_op_url(task_id, "pack")
        return None
    if kind == "scenes_zip":
        scenes_key = _task_value(task, "scenes_key")
        scenes_status = str(_task_value(task, "scenes_status") or "").lower()
        if scenes_status == "skipped":
            return None
        if scenes_key and object_exists(str(scenes_key)):
            return tasks_router._signed_op_url(task_id, "scenes")
        return None
    if kind == "origin_srt":
        key = _task_key(task, "origin_srt_path")
        return tasks_router._signed_op_url(task_id, "origin_srt") if key and object_exists(key) else None
    if kind == "mm_srt":
        key = _task_key(task, "mm_srt_path")
        return tasks_router._signed_op_url(task_id, "mm_srt") if key and object_exists(key) else None
    if kind == "mm_txt":
        mm_key = _task_key(task, "mm_srt_path")
        if not mm_key:
            return None
        txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
        return tasks_router._signed_op_url(task_id, "mm_txt") if object_exists(txt_key) else None
    if kind == "mm_audio":
        key = _task_key(task, "mm_audio_key") or _task_key(task, "mm_audio_path")
        return tasks_router._signed_op_url(task_id, "mm_audio") if key and object_exists(key) else None
    if kind == "edit_bundle_zip":
        publish_key = _task_value(task, "publish_key")
        if publish_key and object_exists(str(publish_key)):
            return get_download_url(str(publish_key))
        return None
    return None


def build_apollo_avatar_publish_hub(task: dict) -> dict[str, object]:
    task_id = str(_task_value(task, "task_id") or _task_value(task, "id") or "")
    deliverables: dict[str, dict[str, str]] = {}
    for key, label in (
        ("pack_zip", "pack.zip"),
        ("scenes_zip", "scenes.zip"),
        ("origin_srt", "origin.srt"),
        ("mm_srt", "mm.srt"),
        ("mm_txt", "mm.txt"),
        ("mm_audio", "mm_audio"),
        ("edit_bundle_zip", "edit_bundle.zip"),
    ):
        url = _deliverable_url(task_id, task, key)
        if url:
            deliverables[key] = {"label": label, "url": url}

    short_code = tasks_router._download_code(task_id)
    short_url = f"/d/{short_code}"

    return {
        "task_id": task_id,
        "gate_enabled": tasks_router._op_gate_enabled(),
        "deliverables": deliverables,
        "copy_bundle": tasks_router._build_copy_bundle(task),
        "download_code": short_code,
        "mobile": {
            "qr_target": short_url,
            "short_link": short_url,
            "short_url": short_url,
            "qr_url": short_url,
        },
        "sop_markdown": tasks_router._publish_sop_markdown(),
        "archive": {
            "publish_provider": _task_value(task, "publish_provider") or "-",
            "publish_key": _task_value(task, "publish_key") or "-",
            "publish_status": _task_value(task, "publish_status") or "-",
            "publish_url": _task_value(task, "publish_url") or "-",
            "published_at": _task_value(task, "published_at") or "-",
        },
    }
