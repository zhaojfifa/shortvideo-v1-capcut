from __future__ import annotations

import logging
from typing import Optional

from gateway.app.routers import tasks as tasks_router
from gateway.app.services.artifact_storage import object_exists

logger = logging.getLogger(__name__)

KIND_MAP = {
    "pack_zip": "pack",
    "scenes_zip": "scenes",
    "origin_srt": "origin_srt",
    "mm_srt": "mm_srt",
    "mm_txt": "mm_txt",
    "mm_audio": "mm_audio",
    "edit_bundle_zip": "publish_bundle",
    "raw_mp4": "raw",
}


def _task_value(task: dict, field: str) -> Optional[str]:
    if isinstance(task, dict):
        return task.get(field)
    return getattr(task, field, None)


def _task_key(task: dict, field: str) -> Optional[str]:
    value = _task_value(task, field)
    return str(value) if value else None


def _deliverable_url(task_id: str, task: dict, key: str) -> Optional[str]:
    kind = KIND_MAP.get(key)
    if not kind:
        return None
    if kind == "raw":
        raw_key = _task_key(task, "raw_path")
        return tasks_router._signed_op_url(task_id, kind) if raw_key and object_exists(raw_key) else None
    if kind == "pack":
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        return tasks_router._signed_op_url(task_id, kind) if pack_key and object_exists(str(pack_key)) else None
    if kind == "scenes":
        scenes_key = _task_value(task, "scenes_key")
        scenes_status = str(_task_value(task, "scenes_status") or "").lower()
        if scenes_status == "skipped":
            return None
        return tasks_router._signed_op_url(task_id, kind) if scenes_key and object_exists(str(scenes_key)) else None
    if kind == "origin_srt":
        origin_key = _task_key(task, "origin_srt_path")
        return tasks_router._signed_op_url(task_id, kind) if origin_key and object_exists(origin_key) else None
    if kind == "mm_srt":
        mm_key = _task_key(task, "mm_srt_path")
        return tasks_router._signed_op_url(task_id, kind) if mm_key and object_exists(mm_key) else None
    if kind == "mm_txt":
        mm_key = _task_key(task, "mm_srt_path")
        if not mm_key:
            return None
        txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
        return tasks_router._signed_op_url(task_id, kind) if object_exists(txt_key) else None
    if kind == "mm_audio":
        audio_key = _task_key(task, "mm_audio_key") or _task_key(task, "mm_audio_path")
        return tasks_router._signed_op_url(task_id, kind) if audio_key and object_exists(audio_key) else None
    if kind == "publish_bundle":
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        return tasks_router._signed_op_url(task_id, kind) if pack_key and object_exists(str(pack_key)) else None
    return None


def build_apollo_avatar_publish_hub(task: dict) -> dict[str, object]:
    task_id = str(_task_value(task, "task_id") or _task_value(task, "id") or "")
    deliverables: dict[str, dict[str, str]] = {}
    resolved = []
    missing = []
    for key, label in (
        ("raw_mp4", "raw.mp4"),
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
            resolved.append(key)
        else:
            missing.append(key)

    short_code = tasks_router._download_code(task_id)
    short_url = f"/d/{short_code}"
    copy_bundle = tasks_router._build_copy_bundle(task)
    copy_bundle["link_text"] = short_url
    sop_markdown = "\n".join(
        [
            "1) Download edit_bundle.zip (recommended) or pack.zip",
            "2) Import into CapCut and finish edits",
            "3) Copy caption/hashtags from Copy Bundle",
            "4) Publish manually",
        ]
    )

    logger.info(
        "apollo_avatar publish_hub deliverables",
        extra={
            "task_id": task_id,
            "resolved": resolved,
            "missing": missing,
            "link_text": short_url,
        },
    )
    return {
        "task_id": task_id,
        "gate_enabled": tasks_router._op_gate_enabled(),
        "deliverables": deliverables,
        "copy_bundle": copy_bundle,
        "download_code": short_code,
        "mobile": {
            "qr_target": short_url,
            "short_link": short_url,
            "short_url": short_url,
            "qr_url": short_url,
        },
        "sop_markdown": sop_markdown,
        "archive": {
            "publish_provider": _task_value(task, "publish_provider") or "-",
            "publish_key": _task_value(task, "publish_key") or "-",
            "publish_status": _task_value(task, "publish_status") or "-",
            "publish_url": _task_value(task, "publish_url") or "-",
            "published_at": _task_value(task, "published_at") or "-",
        },
    }
