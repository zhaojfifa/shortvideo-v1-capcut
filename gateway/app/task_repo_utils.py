"""Helpers for TaskRepository payload normalization and schema mapping."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from gateway.app.schemas import TaskDetail, TaskSummary


DEFAULT_CATEGORY = "beauty"
DEFAULT_CONTENT_LANG = "my"
DEFAULT_UI_LANG = "en"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.utcnow()


def normalize_task_payload(payload: dict[str, Any], *, is_new: bool = False) -> dict[str, Any]:
    task_id = payload.get("task_id") or payload.get("id")
    if not task_id:
        raise ValueError("task payload missing task_id")
    payload["task_id"] = task_id
    payload.setdefault("category_key", DEFAULT_CATEGORY)
    payload.setdefault("content_lang", DEFAULT_CONTENT_LANG)
    payload.setdefault("ui_lang", DEFAULT_UI_LANG)
    payload.setdefault("status", "pending")
    payload.setdefault("face_swap_enabled", False)
    if is_new and not payload.get("created_at"):
        payload["created_at"] = _now_iso()
    payload["updated_at"] = _now_iso()
    return payload


def task_summary_from_payload(payload: dict[str, Any]) -> TaskSummary:
    return TaskSummary(
        task_id=str(payload.get("task_id") or payload.get("id")),
        title=payload.get("title"),
        source_url=payload.get("source_url"),
        source_link_url=payload.get("source_link_url"),
        platform=payload.get("platform"),
        account_id=payload.get("account_id"),
        account_name=payload.get("account_name"),
        video_type=payload.get("video_type"),
        template=payload.get("template"),
        category_key=str(payload.get("category_key") or DEFAULT_CATEGORY),
        content_lang=str(payload.get("content_lang") or DEFAULT_CONTENT_LANG),
        ui_lang=str(payload.get("ui_lang") or DEFAULT_UI_LANG),
        style_preset=payload.get("style_preset"),
        face_swap_enabled=bool(payload.get("face_swap_enabled")),
        status=str(payload.get("status") or "pending"),
        last_step=payload.get("last_step"),
        duration_sec=payload.get("duration_sec"),
        thumb_url=payload.get("thumb_url"),
        pack_path=payload.get("pack_path"),
        created_at=_parse_datetime(payload.get("created_at")),
        error_reason=payload.get("error_reason"),
        error_message=payload.get("error_message"),
        parse_provider=payload.get("parse_provider"),
        subtitles_provider=payload.get("subtitles_provider"),
        dub_provider=payload.get("dub_provider"),
        pack_provider=payload.get("pack_provider"),
        face_swap_provider=payload.get("face_swap_provider"),
        publish_status=payload.get("publish_status"),
        publish_provider=payload.get("publish_provider"),
        publish_key=payload.get("publish_key"),
        publish_url=payload.get("publish_url"),
        published_at=payload.get("published_at"),
        priority=payload.get("priority"),
        assignee=payload.get("assignee"),
        ops_notes=payload.get("ops_notes"),
    )


def task_detail_from_payload(payload: dict[str, Any]) -> TaskDetail:
    summary = task_summary_from_payload(payload)
    return TaskDetail(
        **summary.dict(),
        raw_path=payload.get("raw_path"),
        origin_srt_path=payload.get("origin_srt_path"),
        mm_srt_path=payload.get("mm_srt_path"),
        mm_audio_path=payload.get("mm_audio_path"),
        pack_path=payload.get("pack_path"),
    )


def merge_task_patch(task: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    updated = dict(task)
    updated.update(patch)
    updated["updated_at"] = _now_iso()
    return updated


def sort_tasks_by_created(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tasks, key=lambda t: _parse_datetime(t.get("created_at")), reverse=True)
