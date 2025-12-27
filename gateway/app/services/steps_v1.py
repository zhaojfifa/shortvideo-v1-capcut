"""Reusable pipeline step functions shared by /v1 routes and background tasks."""

import logging
from pathlib import Path

from fastapi import HTTPException

from gateway.app.core.workspace import (
    Workspace,
    pack_zip_path,
    raw_path,
    relative_to_workspace,
    translated_srt_path,
)
from gateway.app.db import SessionLocal
from gateway.app import models
from gateway.app.services.artifact_storage import upload_task_artifact
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.pack import PackError, create_capcut_pack
from gateway.app.services.parse import detect_platform, parse_douyin_video
from gateway.app.services.subtitles import generate_subtitles
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest

logger = logging.getLogger(__name__)

# -------------------------
# Artifact name conventions
# -------------------------
# 强制所有 key 都落到 artifacts/ 下，确保 /files/<key> 路径一致、可预期
RAW_ARTIFACT = "artifacts/raw.mp4"
ORIGIN_SRT_ARTIFACT = "artifacts/origin.srt"
MM_SRT_ARTIFACT = "artifacts/mm.srt"
MM_TXT_ARTIFACT = "artifacts/mm.txt"
MM_AUDIO_ARTIFACT = "artifacts/mm_audio.mp3"
CAPCUT_PACK_ARTIFACT = "artifacts/capcut_pack.zip"


async def run_parse_step(req: ParseRequest):
    """Run the parse step for the given request."""

    try:
        platform = detect_platform(req.link, req.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if platform != "douyin":
        raise HTTPException(
            status_code=400, detail=f"Unsupported platform for V1 parse: {platform}"
        )

    try:
        result = await parse_douyin_video(req.task_id, req.link)

        raw_file = raw_path(req.task_id)
        raw_key = None
        if raw_file.exists():
            raw_key = _upload_artifact(req.task_id, raw_file, RAW_ARTIFACT)

        _update_task(
            req.task_id,
            raw_path=raw_key,
            last_step="parse",
        )
        return result

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in parse step for task %s", req.task_id)
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {exc}") from exc


async def run_subtitles_step(req: SubtitlesRequest):
    """Run the subtitles step for the given request."""

    try:
        result = await generate_subtitles(
            task_id=req.task_id,
            target_lang=req.target_lang,
            force=req.force,
            translate_enabled=req.translate,
            use_ffmpeg_extract=True,
        )

        workspace = Workspace(req.task_id)

        origin_key = None
        mm_key = None

        if workspace.origin_srt_path.exists():
            origin_key = _upload_artifact(req.task_id, workspace.origin_srt_path, ORIGIN_SRT_ARTIFACT)

        # 你的 Workspace 里 mm_srt_path / mm_srt_exists() 可能有差异，这里按“路径存在”判断
        if workspace.mm_srt_path.exists():
            mm_key = _upload_artifact(req.task_id, workspace.mm_srt_path, MM_SRT_ARTIFACT)

            mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
            if mm_txt_path.exists():
                _upload_artifact(req.task_id, mm_txt_path, MM_TXT_ARTIFACT)

        _update_task(
            req.task_id,
            origin_srt_path=origin_key,
            mm_srt_path=mm_key,
            last_step="subtitles",
        )
        return result

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in subtitles step for task %s", req.task_id)
        raise HTTPException(status_code=500, detail="internal error") from exc


async def run_dub_step(req: DubRequest):
    """Run the dubbing step for the given request."""

    workspace = Workspace(req.task_id)
    origin_exists = workspace.origin_srt_path.exists()
    mm_exists = workspace.mm_srt_exists()

    logger.info(
        "Dub request",
        extra={
            "task_id": req.task_id,
            "origin_srt_exists": origin_exists,
            "mm_srt_exists": mm_exists,
            "mm_srt_path": str(workspace.mm_srt_path),
        },
    )

    if not mm_exists:
        raise HTTPException(
            status_code=400,
            detail="translated subtitles not found; run /v1/subtitles first",
        )

    mm_text = workspace.read_mm_srt_text() or ""
    if not mm_text.strip():
        raise HTTPException(
            status_code=400,
            detail="translated subtitles file is empty; please rerun /v1/subtitles",
        )

    try:
        result = await synthesize_voice(
            task_id=req.task_id,
            target_lang=req.target_lang,
            voice_id=req.voice_id,
            force=req.force,
            mm_srt_text=mm_text,
            workspace=workspace,
        )
    except DubbingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # synthesize_voice 可能返回 dict 或其他对象，这里做防御性解析
    audio_path_value = result.get("audio_path") if isinstance(result, dict) else None
    audio_key = None

    if audio_path_value:
        p = Path(audio_path_value)
        if not p.is_absolute():
            # 相对路径时，落到 workspace 的默认输出
            p = workspace.mm_audio_path

        if p.exists():
            audio_key = _upload_artifact(req.task_id, p, MM_AUDIO_ARTIFACT)

    _update_task(req.task_id, mm_audio_path=audio_key, last_step="dub")

    audio_url = f"/v1/tasks/{req.task_id}/audio_mm"
    return {
        "task_id": req.task_id,
        "voice_id": req.voice_id,
        "audio_mm_url": audio_url,
        "duration_sec": result.get("duration_sec") if isinstance(result, dict) else None,
        "audio_path": (result.get("audio_path") or result.get("path")) if isinstance(result, dict) else None,
    }


async def run_pack_step(req: PackRequest):
    """Run the packaging step for the given request."""

    task_id = req.task_id
    workspace = Workspace(task_id)

    raw_file = raw_path(task_id)

    # audio：优先 workspace.mm_audio_path（你的 dub 可能输出 mp3），不存在则 fallback 到 wav 命名
    audio_file = workspace.mm_audio_path
    if not audio_file.exists():
        wav_candidate = (workspace.audio_dir / f"{task_id}_mm_vo.wav") if hasattr(workspace, "audio_dir") else None
        if wav_candidate and wav_candidate.exists():
            audio_file = wav_candidate

    # subs：优先 translated_srt_path(task_id, "my")，fallback "mm"
    subs_mm_srt = translated_srt_path(task_id, "my")
    if not subs_mm_srt.exists():
        subs_mm_srt = translated_srt_path(task_id, "mm")
    subs_mm_txt = subs_mm_srt.with_suffix(".txt")

    try:
        packed = create_capcut_pack(
            task_id,
            raw_file,
            audio_file,
            subs_mm_srt,
            subs_mm_txt,
        )
    except PackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 兼容两类 pack 返回：
    # 1) 新版 pack：内部已 upload，返回 {"zip_key": "...", "zip_path": "...", ...}
    # 2) 旧版 pack：只返回 zip_path / files，本地 zip 在 pack_zip_path(task_id)
    pack_key = None
    if isinstance(packed, dict):
        pack_key = packed.get("zip_key")

    if not pack_key:
        # fallback：从本地 pack_zip_path 上传
        pack_file = pack_zip_path(task_id)
        if pack_file.exists():
            pack_key = _upload_artifact(task_id, pack_file, CAPCUT_PACK_ARTIFACT)

    # 更新任务：pack_path 必须存 key（供 /v1/tasks/{id}/pack 302 → /files/<key>）
    _update_task(
        task_id,
        pack_path=pack_key,
        status="ready",
        last_step="pack",
        error_message=None,
        error_reason=None,
    )

    # 返回值对 UI/调试友好：保留 zip_path/files
    zip_path_value = packed.get("zip_path") if isinstance(packed, dict) else None
    if not zip_path_value:
        pack_file = pack_zip_path(task_id)
        if pack_file.exists():
            zip_path_value = relative_to_workspace(pack_file)

    return {
        "task_id": task_id,
        "zip_key": pack_key,
        "zip_path": zip_path_value,
        "files": packed.get("files") if isinstance(packed, dict) else None,
    }


def _update_task(task_id: str, **fields) -> None:
    """
    注意：这里允许把字段显式更新为 None（例如清理 error_message / error_reason）。
    只要调用方传了 key，就会写入数据库。
    """
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        db.commit()
    finally:
        db.close()


def _upload_artifact(task_id: str, local_path: Path, artifact_name: str) -> str | None:
    """
    返回 storage key（例如 default/default/<task_id>/artifacts/xxx）。
    """
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return None

        # 关键：不要再额外传 task_id=...，避免 wrapper 内部签名变化导致重复参数
        return upload_task_artifact(task, local_path, artifact_name)
    finally:
        db.close()
