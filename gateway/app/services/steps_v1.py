"""Reusable pipeline step functions shared by /v1 routes and background tasks."""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException

from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.core.workspace import (
    Workspace,
    deliver_dir,
    deliver_pack_zip_path,
    raw_path,
    relative_to_workspace,
    translated_srt_path,
)
from gateway.app.db import SessionLocal
from gateway.app import models
from gateway.app.services.artifact_storage import upload_task_artifact
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.parse import detect_platform, parse_video
from gateway.app.services.subtitles import generate_subtitles
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.utils.timing import log_step_timing

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

# -------------------------
# Artifact name conventions
# -------------------------
# 强制所有 key 都落到 artifacts/ 下，确保 /files/<key> 路径一致、可预期
RAW_ARTIFACT = "raw/raw.mp4"
ORIGIN_SRT_ARTIFACT = "subs/origin.srt"
MM_SRT_ARTIFACT = "subs/mm.srt"
MM_TXT_ARTIFACT = "subs/mm.txt"

AUDIO_MM_KEY_TEMPLATE = "deliver/tasks/{task_id}/audio_mm.mp3"

README_TEMPLATE = """CapCut pack usage

1. Create a new CapCut project and import the extracted zip files.
2. Place raw/raw.mp4 on the video track.
3. Import subs/mm.srt and adjust styling.
4. Place audio/{audio_filename} on the audio track and align with subtitles.
5. Add transitions or stickers as needed.
"""


class PackError(Exception):
    """Raised when packing fails."""


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _srt_to_txt(srt_text: str) -> str:
    blocks = [b for b in srt_text.split("\n\n") if b.strip()]
    lines_out: list[str] = []
    for block in blocks:
        text_lines: list[str] = []
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                continue
            if "-->" in s or _SRT_TIME_RE.search(s):
                continue
            text_lines.append(s)
        if text_lines:
            lines_out.append(" ".join(text_lines))
    return "\n".join(lines_out).strip() + ("\n" if lines_out else "")


def _ensure_txt_from_srt(dst_txt: Path, src_srt: Path) -> None:
    srt_text = src_srt.read_text(encoding="utf-8")
    dst_txt.write_text(_srt_to_txt(srt_text), encoding="utf-8")


def _ensure_silence_audio_ffmpeg(out_path: Path, seconds: int = 1) -> None:
    """Create a silent WAV via ffmpeg."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PackError("ffmpeg not found in PATH (required). Please install ffmpeg.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-t",
        str(seconds),
        "-acodec",
        "pcm_s16le",
        str(out_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        raise PackError(f"ffmpeg silence generation failed: {p.stderr[-800:]}")


def _ensure_mp3_audio(src_path: Path, dst_path: Path) -> Path:
    if src_path.suffix.lower() == ".mp3":
        return src_path

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PackError("ffmpeg not found in PATH (required for mp3 conversion).")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src_path),
        "-codec:a",
        "libmp3lame",
        str(dst_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not dst_path.exists() or dst_path.stat().st_size == 0:
        raise PackError(f"ffmpeg mp3 conversion failed: {p.stderr[-800:]}")
    return dst_path


def _maybe_fill_missing_for_pack(*, raw_path: Path, audio_path: Path, subs_path: Path) -> None:
    """Allow pack to proceed by generating silence audio if DUB_SKIP=1."""

    dub_skip = os.getenv("DUB_SKIP", "").strip().lower() in ("1", "true", "yes")
    if not dub_skip:
        return

    if audio_path and not audio_path.exists():
        _ensure_silence_audio_ffmpeg(audio_path, seconds=1)


async def run_parse_step(req: ParseRequest):
    """Run the parse step for the given request."""

    start_time = time.perf_counter()
    platform = None
    try:
        platform = detect_platform(req.link, req.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = await parse_video(req.task_id, req.link, platform_hint=platform)

        raw_file = raw_path(req.task_id)
        raw_key = None
        if raw_file.exists():
            raw_key = _upload_artifact(req.task_id, raw_file, RAW_ARTIFACT)

        _update_task(
            req.task_id,
            raw_path=raw_key,
            platform=(result.get("platform") or platform),
            last_step="parse",
        )
        return result

    except HTTPException as exc:
        _update_task(req.task_id, parse_status="error", parse_error=str(exc.detail))
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in parse step for task %s", req.task_id)
        _update_task(req.task_id, parse_status="error", parse_error=str(exc))
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {exc}") from exc
    finally:
        log_step_timing(
            logger,
            task_id=req.task_id,
            step="parse",
            start_time=start_time,
            provider=platform,
        )


async def run_subtitles_step(req: SubtitlesRequest):
    """Run the subtitles step for the given request."""

    start_time = time.perf_counter()
    asr_backend = os.getenv("ASR_BACKEND") or "whisper"
    subtitles_backend = os.getenv("SUBTITLES_BACKEND") or "gemini"
    logger.info(
        "SUB2_START",
        extra={
            "task_id": req.task_id,
            "step": "subtitles",
            "stage": "SUB2_START",
            "asr_backend": asr_backend,
            "subtitles_backend": subtitles_backend,
            "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
        },
    )
    try:
        _update_task(req.task_id, subtitles_status="running", subtitles_error=None)
        step_timeout_sec = _env_int("SUBTITLES_STEP_TIMEOUT_SEC", 1800)
        result = await asyncio.wait_for(
            generate_subtitles(
                task_id=req.task_id,
                target_lang=req.target_lang,
                force=req.force,
                translate_enabled=req.translate,
                use_ffmpeg_extract=True,
            ),
            timeout=step_timeout_sec,
        )

        workspace = Workspace(req.task_id)

        origin_key = None
        mm_key = None
        mm_txt_key = None

        if workspace.origin_srt_path.exists():
            origin_key = _upload_artifact(req.task_id, workspace.origin_srt_path, ORIGIN_SRT_ARTIFACT)

        # 你的 Workspace 里 mm_srt_path / mm_srt_exists() 可能有差异，这里按“路径存在”判断
        if workspace.mm_srt_path.exists():
            mm_key = _upload_artifact(req.task_id, workspace.mm_srt_path, MM_SRT_ARTIFACT)

            mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
            if mm_txt_path.exists():
                mm_txt_key = _upload_artifact(req.task_id, mm_txt_path, MM_TXT_ARTIFACT)

        subtitles_dir = deliver_dir() / "subtitles" / req.task_id
        subtitles_dir.mkdir(parents=True, exist_ok=True)
        if workspace.origin_srt_path.exists():
            shutil.copy2(workspace.origin_srt_path, subtitles_dir / "origin.srt")
        if workspace.mm_srt_path.exists():
            shutil.copy2(workspace.mm_srt_path, subtitles_dir / "mm.srt")
        if workspace.segments_json.exists():
            shutil.copy2(workspace.segments_json, subtitles_dir / "subtitles.json")
        subtitles_key = relative_to_workspace(subtitles_dir / "subtitles.json")

        _update_task(
            req.task_id,
            origin_srt_path=origin_key,
            mm_srt_path=mm_key,
            last_step="subtitles",
            subtitles_status="ready",
            subtitles_key=subtitles_key,
            subtitle_structure_path=subtitles_key,
            subtitles_error=None,
        )
        logger.info(
            "SUB2_DONE",
            extra={
                "task_id": req.task_id,
                "step": "subtitles",
                "stage": "SUB2_DONE",
                "asr_backend": asr_backend,
                "subtitles_backend": subtitles_backend,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "origin_srt_key": origin_key,
                "mm_srt_key": mm_key,
                "mm_txt_key": mm_txt_key,
                "subtitles_key": subtitles_key,
            },
        )
        return result

    except asyncio.TimeoutError:
        _update_task(req.task_id, subtitles_status="error", subtitles_error="timeout")
        raise HTTPException(status_code=504, detail="subtitles timeout")
    except asyncio.CancelledError:
        _update_task(req.task_id, subtitles_status="error", subtitles_error="cancelled")
        raise
    except HTTPException as exc:
        _update_task(req.task_id, subtitles_status="error", subtitles_error=str(exc.detail))
        raise
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in subtitles step for task %s", req.task_id)
        _update_task(req.task_id, subtitles_status="error", subtitles_error=str(exc))
        raise HTTPException(status_code=500, detail="internal error") from exc
    finally:
        provider = os.getenv("SUBTITLES_BACKEND", None)
        log_step_timing(
            logger,
            task_id=req.task_id,
            step="subtitles",
            start_time=start_time,
            provider=provider,
        )


async def run_dub_step(req: DubRequest):
    """Run the dubbing step for the given request."""

    start_time = time.perf_counter()
    provider = os.getenv("DUB_PROVIDER", None)
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
    logger.info(
        "DUB3_START",
        extra={
            "task_id": req.task_id,
            "step": "dub",
            "stage": "DUB3_START",
            "dub_provider": provider,
            "voice_id": req.voice_id,
            "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
        },
    )

    if not mm_exists:
        detail = "translated subtitles not found; run /api/tasks/{task_id}/subtitles first"
        _update_task(req.task_id, dub_status="error", dub_error=detail)
        raise HTTPException(status_code=400, detail=detail)

    override_text = (req.mm_text or "").strip()
    mm_text = override_text or (workspace.read_mm_srt_text() or "")
    logger.info(
        "DUB3_TEXT_SOURCE",
        extra={
            "task_id": req.task_id,
            "step": "dub",
            "stage": "DUB3_TEXT_SOURCE",
            "dub_provider": provider,
            "voice_id": req.voice_id,
            "text_source": "override" if override_text else "mm_srt",
            "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
            "text_len": len(mm_text or ""),
        },
    )
    if not mm_text.strip():
        detail = "translated subtitles file is empty; please rerun /api/tasks/{task_id}/subtitles"
        _update_task(req.task_id, dub_status="error", dub_error=detail)
        raise HTTPException(status_code=400, detail=detail)

    try:
        step_timeout_sec = _env_int("DUB_STEP_TIMEOUT_SEC", 900)
        result = await asyncio.wait_for(
            synthesize_voice(
                task_id=req.task_id,
                target_lang=req.target_lang,
                voice_id=req.voice_id,
                force=req.force,
                mm_srt_text=mm_text,
                workspace=workspace,
            ),
            timeout=step_timeout_sec,
        )
    except asyncio.TimeoutError:
        _update_task(req.task_id, dub_status="error", dub_error="timeout")
        raise HTTPException(status_code=504, detail="dub timeout")
    except asyncio.CancelledError:
        _update_task(req.task_id, dub_status="error", dub_error="cancelled")
        raise
    except DubbingError as exc:
        _update_task(req.task_id, dub_status="error", dub_error=str(exc))
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
            mp3_path = _ensure_mp3_audio(p, workspace.mm_audio_mp3_path)
            key_template = AUDIO_MM_KEY_TEMPLATE.format(task_id=req.task_id)
            storage = get_storage_service()
            uploaded_key = storage.upload_file(
                str(mp3_path),
                key_template,
                content_type="audio/mpeg",
            )
            if not uploaded_key:
                detail = "Audio upload failed; no storage key returned"
                _update_task(req.task_id, dub_status="error", dub_error=detail)
                raise HTTPException(status_code=500, detail=detail)
            audio_key = uploaded_key
            logger.info(
                "DUB3_UPLOAD_DONE",
                extra={
                    "task_id": req.task_id,
                    "step": "dub",
                    "stage": "DUB3_UPLOAD_DONE",
                    "dub_provider": provider,
                    "voice_id": req.voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "output_path": str(mp3_path),
                    "output_size": mp3_path.stat().st_size if mp3_path.exists() else None,
                },
            )

    if audio_key:
        _update_task(
            req.task_id,
            mm_audio_path=audio_key,
            mm_audio_key=audio_key,
            last_step="dub",
        )

    edited_text = workspace.read_mm_edited_text()
    if edited_text and edited_text.strip():
        mm_txt_path = workspace.mm_txt_path
        mm_txt_path.parent.mkdir(parents=True, exist_ok=True)
        mm_txt_path.write_text(edited_text, encoding="utf-8")
        _upload_artifact(req.task_id, mm_txt_path, MM_TXT_ARTIFACT)

    try:
        audio_url = f"/v1/tasks/{req.task_id}/audio_mm"
        resp = {
            "task_id": req.task_id,
            "voice_id": req.voice_id,
            "audio_mm_url": audio_url,
            "duration_sec": result.get("duration_sec") if isinstance(result, dict) else None,
            "audio_path": (result.get("audio_path") or result.get("path")) if isinstance(result, dict) else None,
        }
        logger.info(
            "DUB3_DONE",
            extra={
                "task_id": req.task_id,
                "step": "dub",
                "stage": "DUB3_DONE",
                "dub_provider": provider,
                "voice_id": req.voice_id,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "audio_key": audio_key,
            },
        )
        return resp
    finally:
        log_step_timing(
            logger,
            task_id=req.task_id,
            step="dub",
            start_time=start_time,
            provider=provider,
            voice_id=req.voice_id,
        )


async def run_pack_step(req: PackRequest):
    """Run the packaging step for the given request."""

    start_time = time.perf_counter()
    task_id = req.task_id
    workspace = Workspace(task_id)

    raw_file = raw_path(task_id)
    zip_path = deliver_pack_zip_path(task_id)
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # audio：优先 workspace.mm_audio_path（你的 dub 可能输出 mp3），不存在则 fallback 到 wav 命名
    audio_file = workspace.mm_audio_path
    audio_key = _get_task_mm_audio_key(task_id)
    if audio_key and not audio_file.exists():
        storage = get_storage_service()
        target_path = workspace.mm_audio_mp3_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        storage.download_file(audio_key, str(target_path))
        audio_file = target_path
    if not audio_file.exists():
        wav_candidate = (workspace.audio_dir / f"{task_id}_mm_vo.wav") if hasattr(workspace, "audio_dir") else None
        if wav_candidate and wav_candidate.exists():
            audio_file = wav_candidate

    # subs：优先 translated_srt_path(task_id, "my")，fallback "mm"
    subs_mm_srt = translated_srt_path(task_id, "my")
    if not subs_mm_srt.exists():
        subs_mm_srt = translated_srt_path(task_id, "mm")
    try:
        _maybe_fill_missing_for_pack(
            raw_path=raw_file,
            audio_path=audio_file,
            subs_path=subs_mm_srt,
        )

        required = [raw_file, audio_file, subs_mm_srt]
        missing = [p for p in required if not p.exists()]
        if missing:
            names = ", ".join(str(p) for p in missing)
            raise PackError(f"missing required files: {names}")

        audio_filename = audio_file.name

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"pack_{task_id}"
            tmp_path.mkdir(parents=True, exist_ok=True)

            raw_dir = tmp_path / "raw"
            audio_dir = tmp_path / "audio"
            subs_dir = tmp_path / "subs"
            scenes_dir = tmp_path / "scenes"
            for d in (raw_dir, audio_dir, subs_dir, scenes_dir):
                d.mkdir(parents=True, exist_ok=True)

            audio_ext = audio_file.suffix if audio_file.suffix else ".wav"
            audio_filename = f"voice_my{audio_ext}"

            shutil.copy(raw_file, raw_dir / "raw.mp4")
            shutil.copy(audio_file, audio_dir / audio_filename)
            shutil.copy(subs_mm_srt, subs_dir / "mm.srt")

            mm_txt_path = subs_mm_srt.with_suffix(".txt")
            if mm_txt_path.exists():
                shutil.copy(mm_txt_path, subs_dir / "mm.txt")
            else:
                _ensure_txt_from_srt(subs_dir / "mm.txt", subs_mm_srt)

            (scenes_dir / ".keep").write_text("", encoding="utf-8")

            manifest = {
                "version": "1.8",
                "pack_type": "capcut_v18",
                "task_id": task_id,
                "language": "my",
                "assets": {
                    "raw_video": "raw/raw.mp4",
                    "voice": f"audio/{audio_filename}",
                    "subtitle": "subs/mm.srt",
                    "scenes_dir": "scenes/",
                },
            }
            (tmp_path / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (tmp_path / "README.md").write_text(
                README_TEMPLATE.format(audio_filename=audio_filename),
                encoding="utf-8",
            )

            pack_prefix = Path("deliver") / "packs" / task_id
            with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
                for item in tmp_path.rglob("*"):
                    if item.is_file():
                        arcname = (pack_prefix / item.relative_to(tmp_path)).as_posix()
                        zf.write(item, arcname=arcname)
    except PackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not zip_path.exists():
        raise RuntimeError(f"Pack zip not found after packing: {zip_path}")

    zip_key = f"packs/{task_id}/capcut_pack.zip"
    storage = get_storage_service()
    storage.upload_file(str(zip_path), zip_key, content_type="application/zip")

    files = [
        f"deliver/packs/{task_id}/raw/raw.mp4",
        f"deliver/packs/{task_id}/audio/{audio_filename}",
        f"deliver/packs/{task_id}/subs/mm.srt",
        f"deliver/packs/{task_id}/subs/mm.txt",
        f"deliver/packs/{task_id}/scenes/.keep",
        f"deliver/packs/{task_id}/manifest.json",
        f"deliver/packs/{task_id}/README.md",
    ]

    # 更新任务：pack_path 必须存 key（供 /v1/tasks/{id}/pack 302 → /files/<key>）
    _update_task(
        task_id,
        pack_key=zip_key,
        pack_type="capcut_v18",
        pack_status="ready",
        pack_path=None,
        status="ready",
        last_step="pack",
        error_message=None,
        error_reason=None,
    )

    # 返回值对 UI/调试友好：保留 zip_path/files
    zip_path_value = relative_to_workspace(zip_path) if zip_path.exists() else None
    try:
        download_url = storage.generate_presigned_url(
            zip_key,
            expiration=3600,
            content_type="application/zip",
            filename=f"{task_id}_capcut_pack.zip",
            disposition="attachment",
        )
    except TypeError:
        download_url = storage.generate_presigned_url(zip_key, expiration=3600)
    resp = {
        "task_id": task_id,
        "zip_key": zip_key,
        "pack_key": zip_key,
        "zip_path": zip_path_value,
        "download_url": download_url,
        "files": files,
    }
    try:
        return resp
    finally:
        log_step_timing(
            logger,
            task_id=req.task_id,
            step="pack",
            start_time=start_time,
        )


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


def _get_task_mm_audio_key(task_id: str) -> str | None:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return None
        return getattr(task, "mm_audio_key", None) or getattr(task, "mm_audio_path", None)
    finally:
        db.close()
