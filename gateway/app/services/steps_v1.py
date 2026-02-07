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
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException
import httpx

from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.core.workspace import (
    Workspace,
    deliver_dir,
    deliver_pack_zip_path,
    raw_path,
    relative_to_workspace,
    task_base_dir,
    translated_srt_path,
)
from gateway.app.db import SessionLocal
from gateway.app import config, models
from gateway.app.services.artifact_storage import upload_task_artifact, get_download_url, object_exists
from gateway.app.services.task_events import append_task_event as _append_task_event
from gateway.app.services.status_policy.registry import get_status_policy
from gateway.app.services.status_policy.utils import policy_upsert
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.parse import detect_platform, parse_video
from gateway.app.services.publish_service import publish_task_pack
from gateway.app.services.scene_split import run_scenes_build
from gateway.app.services.subtitles import generate_subtitles
from gateway.app.utils.pipeline_config import parse_pipeline_config, pipeline_config_to_storage
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.utils.timing import log_step_timing

logger = logging.getLogger(__name__)


def _append_event(repo, task_id: str, *, channel: str, code: str, message: str, extra=None) -> None:
    task = repo.get(task_id)
    if not task:
        return
    _append_task_event(
        task,
        channel=channel,
        code=code,
        message=message,
        extra=extra,
    )
    policy_upsert(
        repo,
        task_id,
        task,
        {"events": task.get("events") or []},
        step="steps_v1.event",
        force=False,
    )


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _truthy_env(name: str, default: str = "1") -> bool:
    v = os.getenv(name, default)
    return v is not None and v.strip().lower() not in ("0", "false", "no", "")


async def _hydrate_raw_from_url(
    *,
    task_id: str,
    task: dict,
    final_video_url: str | None,
    repo,
    force: bool = False,
) -> str:
    raw_file = raw_path(task_id)
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_key = task.get("raw_path")

    if raw_key and not force:
        if raw_file.exists():
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="hydrate_raw.skip",
                message="Raw already present; skip hydrate",
                extra={"raw_key": raw_key},
            )
            return raw_key
        try:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="hydrate_raw.start",
                message="Hydrate raw from storage",
                extra={"raw_key": raw_key, "source": "storage"},
            )
            storage = get_storage_service()
            storage.download_file(raw_key, str(raw_file))
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="hydrate_raw.done",
                message="Hydrate raw done",
                extra={"raw_key": raw_key, "source": "storage"},
            )
            return raw_key
        except Exception as exc:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="hydrate_raw.error",
                message="Hydrate raw from storage failed",
                extra={"raw_key": raw_key, "source": "storage", "message": str(exc)},
            )
            if not final_video_url:
                raise

    if not final_video_url:
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="hydrate_raw.error",
            message="Missing final_video_url for raw hydrate",
        )
        raise RuntimeError("final_video_url missing for raw hydrate")

    host = urlparse(final_video_url).netloc if final_video_url else ""
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="hydrate_raw.start",
        message="Hydrate raw from url",
        extra={"source": "url", "source_host": host},
    )
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(final_video_url)
        resp.raise_for_status()
        raw_file.write_bytes(resp.content)
    raw_key = upload_task_artifact(task, raw_file, "raw.mp4", task_id=task_id)
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="hydrate_raw.done",
        message="Hydrate raw done",
        extra={"raw_key": raw_key, "source": "url", "source_host": host},
    )
    return raw_key


def _truthy_env(name: str, default: str = "1") -> bool:
    v = os.getenv(name, default)
    return v is not None and v.strip().lower() not in ("0", "false", "no", "")

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


def _clean_text_for_dub(text: str) -> str:
    return re.sub(r"[\W_]+", "", text or "", flags=re.UNICODE)


def _write_no_dub_note(task_id: str, reason: str) -> Path:
    note_path = task_base_dir(task_id) / "dub" / "no_dub.txt"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    note_path.write_text(f"{ts} reason={reason}\n", encoding="utf-8")
    return note_path


def _ensure_silent_wav(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=mono:sample_rate=24000",
            "-t",
            "0.2",
            "-q:a",
            "9",
            "-acodec",
            "pcm_s16le",
            str(path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and path.exists():
            return
    # Fallback: create empty placeholder
    path.write_bytes(b"")


def _skip_dub_ready(req: DubRequest, workspace: Workspace, reason: str, provider: str | None) -> dict:
    _write_no_dub_note(req.task_id, reason)
    audio_path = workspace.mm_audio_primary_path
    _ensure_silent_wav(audio_path)

    audio_key = None
    try:
        mp3_path = _ensure_mp3_audio(audio_path, workspace.mm_audio_mp3_path)
        key_template = AUDIO_MM_KEY_TEMPLATE.format(task_id=req.task_id)
        storage = get_storage_service()
        uploaded_key = storage.upload_file(
            str(mp3_path),
            key_template,
            content_type="audio/mpeg",
        )
        if uploaded_key:
            audio_key = uploaded_key
    except Exception as exc:  # pragma: no cover
        logger.warning("DUB3_SKIP upload failed: %s", exc)

    if audio_key:
        _update_task(
            req.task_id,
            mm_audio_path=audio_key,
            mm_audio_key=audio_key,
            last_step="dub",
            dub_status="ready",
            dub_error=None,
        )
    else:
        _update_task(
            req.task_id,
            last_step="dub",
            dub_status="ready",
            dub_error=None,
        )

    _update_pipeline_config(req.task_id, {"no_dub": "true", "dub_skip_reason": reason})

    logger.info(
        "DUB3_SKIP",
        extra={
            "task_id": req.task_id,
            "step": "dub",
            "stage": "DUB3_SKIP",
            "dub_provider": provider,
            "reason": reason,
        },
    )
    return {
        "task_id": req.task_id,
        "voice_id": req.voice_id,
        "audio_mm_url": f"/v1/tasks/{req.task_id}/audio_mm",
        "no_dub": True,
        "dub_skip_reason": reason,
    }


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
        step_timeout_sec = _env_int("SUBTITLES_STEP_TIMEOUT_SEC", 7200)
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
        probe = result.get("stream_probe") if isinstance(result, dict) else None
        clean_generated = bool(result.get("clean_video_generated")) if isinstance(result, dict) else False
        no_subtitles_flag = bool(result.get("no_subtitles")) if isinstance(result, dict) else False
        updates: dict[str, str] = {}
        if no_subtitles_flag:
            updates["no_subtitles"] = "true"
        if isinstance(probe, dict):
            has_audio = probe.get("has_audio")
            if has_audio is True:
                updates["has_audio"] = "true"
            elif has_audio is False:
                updates["has_audio"] = "false"
            has_sub = probe.get("has_subtitle_stream")
            if has_sub is True:
                updates["subtitle_stream"] = "true"
            elif has_sub is False:
                updates["subtitle_stream"] = "false"
            subtitle_codecs = probe.get("subtitle_codecs") or []
            if isinstance(subtitle_codecs, list) and subtitle_codecs:
                updates["subtitle_codecs"] = ",".join([str(v) for v in subtitle_codecs if str(v).strip()])
            audio_codecs = probe.get("audio_codecs") or []
            if isinstance(audio_codecs, list) and audio_codecs:
                updates["audio_codecs"] = ",".join([str(v) for v in audio_codecs if str(v).strip()])
        if clean_generated:
            updates["clean_video_generated"] = "true"
        _update_pipeline_config(req.task_id, updates)

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
        _update_task(
            req.task_id,
            subtitles_status="error",
            subtitles_error=f"{exc.status_code}: {exc.detail}",
        )
        logger.error(
            "Subtitles failed",
            extra={
                "task_id": req.task_id,
                "step": "subtitles",
                "phase": "exception",
                "provider": subtitles_backend,
            },
            exc_info=True,
        )
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

    pipeline_config = {}
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == req.task_id).first()
        if task:
            pipeline_config = parse_pipeline_config(task.pipeline_config)
    finally:
        db.close()

    if pipeline_config.get("no_subtitles") == "true":
        return _skip_dub_ready(req, workspace, "no_subtitles", provider)

    mm_txt_path = workspace.mm_txt_path
    if not mm_txt_path.exists():
        return _skip_dub_ready(req, workspace, "mm_txt_missing", provider)
    try:
        mm_txt_text = mm_txt_path.read_text(encoding="utf-8")
    except Exception:
        return _skip_dub_ready(req, workspace, "mm_txt_missing", provider)
    if mm_txt_text.strip().lower() == "no subtitles":
        return _skip_dub_ready(req, workspace, "no_subtitles_marker", provider)
    if not mm_txt_text.strip():
        return _skip_dub_ready(req, workspace, "mm_txt_empty", provider)

    override_text = (req.mm_text or "").strip()
    mm_text = override_text or mm_txt_text
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
    if not mm_text.strip() or not _clean_text_for_dub(mm_text):
        return _skip_dub_ready(req, workspace, "mm_text_empty", provider)

    step_timeout_sec = _env_int("DUB_STEP_TIMEOUT_SEC", 900)
    try:
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
        return _skip_dub_ready(req, workspace, "tts_failed:timeout", provider)
    except asyncio.CancelledError:
        return _skip_dub_ready(req, workspace, "tts_failed:cancelled", provider)
    except DubbingError as exc:
        return _skip_dub_ready(req, workspace, f"tts_failed:{str(exc)[:80]}", provider)
    except HTTPException as exc:
        return _skip_dub_ready(req, workspace, f"tts_failed:{exc.status_code}", provider)
    except Exception as exc:  # pragma: no cover
        return _skip_dub_ready(req, workspace, f"tts_failed:{str(exc)[:80]}", provider)

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
            dub_status="ready",
            dub_error=None,
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


def compute_subtitles_params(task: dict, payload) -> tuple[str, bool, bool]:
    target_lang = (payload.target_lang if payload else None) or task.get("content_lang") or "my"
    force = payload.force if payload else False
    translate = payload.translate if payload else True
    pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
    if pipeline_config.get("subtitles_mode") == "whisper-only":
        translate = False
    return target_lang, bool(force), bool(translate)


async def run_subtitles_step_entry(
    *,
    task_id: str,
    target_lang: str,
    force: bool,
    translate: bool,
):
    return await run_subtitles_step(
        SubtitlesRequest(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate=translate,
        )
    )


async def run_apollo_avatar_generate_step(
    *,
    task: dict,
    task_id: str,
    req,
    repo,
    live_enabled: bool,
    force: bool = False,
) -> dict:
    try:
        from gateway.app.services.apollo_avatar_service import ApolloAvatarService
    except Exception as e:
        append_task_event(
            repo,
            task_id,
            "AVATAR_IMPORT_ERROR",
            f"Import ApolloAvatarService failed: {e}",
            level="error",
        )
        raise
    provider_name = getattr(config.settings, "apollo_avatar_provider", "fal_wan26_flash")
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="prepare.start",
        message="Prepare start",
        extra={"task_id": task_id},
    )
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="generate.start",
        message="Generate start",
        extra={
            "provider": provider_name,
            "model": getattr(config.settings, "apollo_avatar_live_model", None),
            "target_duration_sec": getattr(req, "target_duration_sec", None),
            "seed": getattr(req, "seed", None),
            "live": bool(live_enabled),
        },
    )
    existing_final = (
        task.get("apollo_avatar_final_video_key")
        or (task.get("apollo_avatar") or {}).get("final_video_url")
        or (task.get("apollo_avatar") or {}).get("final_video_key")
    )
    if existing_final and not force:
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="generate.skip",
            message="Generate skipped (existing result)",
            extra={"final_video_url": existing_final, "provider": provider_name},
        )
        return {
            "ok": True,
            "task_id": task_id,
            "segments": (task.get("apollo_avatar") or {}).get("segments", []),
            "final_video_url": existing_final,
            "manifest_url": (task.get("apollo_avatar") or {}).get("manifest_url"),
        }
    service = ApolloAvatarService(repo=repo)
    try:
        artifacts = await service.generate_stitch_only(task, req, live_enabled=live_enabled)
    except Exception as exc:
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="generate.error",
            message="Generate error",
            extra={
                "provider": provider_name,
                "stage": "generate",
                "message": str(exc),
                "live": bool(live_enabled),
                "model": getattr(config.settings, "apollo_avatar_live_model", None),
            },
        )
        raise
    first_req_id = None
    if getattr(artifacts, "segments", None):
        for seg in artifacts.segments:
            if getattr(seg, "request_id", None):
                first_req_id = seg.request_id
                break
    if live_enabled and not first_req_id:
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="generate.error",
            message="Generate error: missing request_id",
            extra={
                "provider": provider_name,
                "stage": "generate",
                "message": "missing request_id",
                "live": True,
            },
        )
        raise RuntimeError("Live generate missing request_id")
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="generate.done",
        message="Generate done",
        extra={
            "provider": provider_name,
            "request_id": first_req_id,
            "final_video_url": getattr(artifacts, "final_video_url", None),
        },
    )

    plan = getattr(artifacts, "plan", None)
    segments = []
    if plan and getattr(plan, "segments", None):
        segments = [
            {"idx": s.idx, "duration_sec": s.duration_sec}
            for s in plan.segments
            if s is not None
        ]
    if segments:
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="slice.done",
            message="Slice done",
            extra={"segments": segments},
        )

    raw_key = None
    final_url = getattr(artifacts, "final_video_url", None)
    if final_url or task.get("raw_path"):
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="assemble.start",
            message="Assemble start",
        )
        try:
            raw_key = await _hydrate_raw_from_url(
                task_id=task_id,
                task=task,
                final_video_url=final_url,
                repo=repo,
                force=force,
            )
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="assemble.done",
                message="Assemble done",
                extra={"raw_key": raw_key},
            )
        except Exception as exc:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="assemble.error",
                message="Assemble error",
                extra={"error": str(exc)},
            )
            raise

    def _dump(obj):
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return obj

    policy_upsert(
        repo,
        task_id,
        task,
        {
            "last_step": "apollo_avatar_generate",
            "status": "processing",
            "apollo_avatar_manifest_key": artifacts.manifest_url,
            "apollo_avatar_final_video_key": artifacts.final_video_url,
            "apollo_avatar": _dump(artifacts),
            "raw_path": raw_key,
        },
        step="steps_v1.apollo_avatar_generate",
        force=force,
    )
    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="prepare.done",
        message="Prepare done",
        extra={"raw_key": raw_key},
    )
    return {
        "ok": True,
        "task_id": task_id,
        "segments": [_dump(s) for s in (getattr(artifacts, "segments", None) or [])],
        "final_video_url": artifacts.final_video_url,
        "manifest_url": artifacts.manifest_url,
    }


async def run_post_generate_pipeline(
    *,
    task_id: str,
    repo,
    target_lang: str | None = None,
    translate: bool | None = None,
    voice_id: str | None = None,
    force: bool = False,
):
    """
    After a task got its raw.mp4 hydrated (apollo_avatar_generate),
    run subtitles -> dub -> pack in order.

    - Idempotent: skips steps already ready.
    - Extensible: centralized orchestration for future kinds/steps.
    """

    if not _truthy_env("AUTO_RUN_PIPELINE_AFTER_GENERATE", "1"):
        logger.info(
            "AUTO_RUN_PIPELINE_AFTER_GENERATE disabled; skip post-generate pipeline",
            extra={"task_id": task_id},
        )
        return

    task = repo.get(task_id)
    if not task:
        logger.warning("Task not found in post-generate pipeline", extra={"task_id": task_id})
        return

    is_apollo = str(task.get("kind") or task.get("category_key") or task.get("platform") or "").lower() == "apollo_avatar"
    pack_key = task.get("pack_key") or task.get("pack_path")
    pack_status = str(task.get("pack_status") or "").lower()
    if pack_key and pack_status in {"ready", "done"} and not force:
        task = policy_upsert(
            repo,
            task_id,
            task,
            {
                "status": "done",
                "last_step": task.get("last_step") or "pack",
            },
            step="steps_v1.post_pipeline",
            force=force,
        )
        return

    pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
    raw_key = task.get("raw_path")
    raw_file = raw_path(task_id)
    if raw_key and not raw_file.exists():
        try:
            storage = get_storage_service()
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            storage.download_file(raw_key, str(raw_file))
        except Exception as exc:
            logger.exception(
                "Failed to hydrate raw file from raw_key before post pipeline",
                extra={"task_id": task_id, "raw_key": raw_key, "error": str(exc)},
            )
            return

    _target_lang = target_lang or task.get("content_lang") or "my"
    _translate = True if translate is None else bool(translate)
    if pipeline_config.get("subtitles_mode") == "whisper-only":
        _translate = False

    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="post.start",
        message="Post pipeline start",
    )

    # Status policy hook (no-op by default; apollo_avatar prevents READY regression when publish bundle exists)
    _policy = get_status_policy(task)

    def _update(fields: dict) -> None:
        nonlocal task
        task = policy_upsert(
            repo,
            task_id,
            task,
            dict(fields or {}),
            step="steps_v1.update",
            force=force,
        )
        # refresh local cache to avoid stale merges across steps
        task = repo.get(task_id) or task

    # --------- Step 1: Subtitles ---------
    subtitles_ready = (task.get("subtitles_status") == "ready") and bool(task.get("subtitles_key"))
    if not subtitles_ready or force:
        try:
            await run_subtitles_step_entry(
                task_id=task_id,
                target_lang=_target_lang,
                force=force,
                translate=_translate,
            )
        except Exception:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.error",
                message="Subtitles failed",
                extra={"stage": "subtitles"},
            )
            logger.exception("Post-generate subtitles failed", extra={"task_id": task_id})
            _update(
                {
                    "subtitles_status": "failed",
                    "status": "failed",
                    "last_step": "subtitles",
                    "error_message": "subtitles_failed",
                    "error_reason": "subtitles_failed",
                }
            )
            return
    else:
        logger.info("Post-generate: subtitles already ready; skip", extra={"task_id": task_id})

    task = repo.get(task_id) or task
    pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
    subtitles_key = task.get("subtitles_key") or task.get("mm_srt_path")
    if subtitles_key:
        _update(
            {
                "subtitles_key": subtitles_key,
                "subtitles_status": "done",
                "subtitles_provider": task.get("subtitles_provider") or "gemini",
            }
        )

    # --------- Step 2: Dub ---------
    audio_key = task.get("mm_audio_key") or task.get("mm_audio_path")
    dub_ready = (task.get("dub_status") == "ready") and bool(audio_key)
    if not dub_ready or force:
        try:
            _voice_id = voice_id or pipeline_config.get("voice_id") or pipeline_config.get("dub_voice_id")
            await run_dub_step(
                DubRequest(
                    task_id=task_id,
                    voice_id=_voice_id,
                    force=force,
                )
            )
        except Exception:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.error",
                message="Dub failed",
                extra={"stage": "dub"},
            )
            logger.exception("Post-generate dub failed", extra={"task_id": task_id})
            _update(
                {
                    "dub_status": "failed",
                    "status": "failed",
                    "last_step": "dub",
                    "error_message": "dub_failed",
                    "error_reason": "dub_failed",
                }
            )
            return
    else:
        logger.info("Post-generate: dub already ready; skip", extra={"task_id": task_id})

    task = repo.get(task_id) or task
    audio_key = task.get("mm_audio_key") or task.get("mm_audio_path")
    if audio_key:
        _update(
            {
                "dub_status": "done",
                "dub_provider": task.get("dub_provider") or "edge-tts",
            }
        )

    # --------- Step 3: Scenes ---------
    scenes_key = task.get("scenes_key")
    scenes_ready = (task.get("scenes_status") == "ready") and bool(scenes_key)
    if is_apollo:
        _update({"scenes_status": "skipped", "scenes_error": None})
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="post.scenes.skip",
            message="Scenes skipped (not applicable)",
        )
    elif not scenes_ready or force:
        logger.info("APOLLO_AVATAR_BUILD_SCENES_START", extra={"task_id": task_id})
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="post.scenes.start",
            message="Scenes build start",
        )
        try:
            res = run_scenes_build(task_id, _update)
            scenes_key = res.get("scenes_key")
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.scenes.done",
                message="Scenes build done",
                extra={"scenes_key": scenes_key},
            )
            logger.info(
                "APOLLO_AVATAR_BUILD_SCENES_DONE",
                extra={"task_id": task_id, "scenes_key": scenes_key},
            )
        except Exception as exc:
            _update({"scenes_status": "failed", "scenes_error": str(exc)})
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.scenes.error",
                message="Scenes build failed",
                extra={"stage": "scenes"},
            )
            logger.exception("Post-generate scenes failed", extra={"task_id": task_id})
    else:
        logger.info("Post-generate: scenes already ready; skip", extra={"task_id": task_id})

    task = repo.get(task_id) or task
    if str(task.get("scenes_status") or "").lower() == "ready":
        _update({"scenes_status": "done"})

    # --------- Step 3: Pack ---------
    pack_key = task.get("pack_key") or task.get("pack_path")
    pack_ready = (task.get("pack_status") == "ready") and bool(pack_key)
    if not pack_ready or force:
        logger.info("APOLLO_AVATAR_BUILD_PACK_START", extra={"task_id": task_id})
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="post.pack.start",
            message="Pack build start",
        )
        try:
            pack_resp = await run_pack_step(PackRequest(task_id=task_id))
            task = repo.get(task_id) or task
            pack_key = (
                (pack_resp or {}).get("pack_key")
                or task.get("pack_key")
                or task.get("pack_path")
            )
            if pack_key:
                _update(
                    {
                        "pack_key": pack_key,
                        "pack_status": "done",
                        "pack_provider": task.get("pack_provider") or "capcut",
                    }
                )
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.pack.done",
                message="Pack build done",
                extra={"pack_key": pack_key},
            )
            logger.info(
                "APOLLO_AVATAR_BUILD_PACK_DONE",
                extra={"task_id": task_id, "pack_key": pack_key},
            )
        except Exception:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.error",
                message="Pack failed",
                extra={"stage": "pack"},
            )
            logger.exception("Post-generate pack failed", extra={"task_id": task_id})
            _update(
                {
                    "pack_status": "failed",
                    "status": "failed",
                    "last_step": "pack",
                    "error_message": "pack_failed",
                    "error_reason": "pack_failed",
                }
            )
            return
    else:
        logger.info("Post-generate: pack already ready; skip", extra={"task_id": task_id})

    task = repo.get(task_id) or task
    if str(task.get("pack_status") or "").lower() == "ready":
        _update({"pack_status": "done", "pack_provider": task.get("pack_provider") or "capcut"})

    # --------- Step 4: Publish bundle ---------
    publish_key = task.get("publish_key")
    publish_ready = (task.get("publish_status") == "ready") and bool(publish_key)
    if not publish_ready or force:
        logger.info("APOLLO_AVATAR_BUILD_PUBLISH_BUNDLE_START", extra={"task_id": task_id})
        _append_event(
            repo,
            task_id,
            channel="apollo_avatar",
            code="post.publish.start",
            message="Publish bundle build start",
        )
        db = SessionLocal()
        try:
            res = publish_task_pack(task_id, db, task_repo=repo, provider=None, force=force)
            publish_key = res.get("publish_key")
            publish_provider = res.get("provider")
            publish_url = res.get("download_url") or ""
            uploaded = False
            if publish_key and not object_exists(str(publish_key)):
                local_path = Path(str(publish_key))
                if local_path.exists():
                    uploaded_key = upload_task_artifact(
                        task, local_path, "deliver/publish/capcut_pack.zip", task_id=task_id
                    )
                    publish_key = uploaded_key
                    publish_provider = "artifact"
                    publish_url = get_download_url(str(uploaded_key))
                    uploaded = True
            task_db = db.query(models.Task).filter(models.Task.id == task_id).first()
            if task_db and not uploaded:
                _update(
                    {
                        "publish_provider": task_db.publish_provider,
                        "publish_key": task_db.publish_key,
                        "publish_url": task_db.publish_url,
                        "publish_status": task_db.publish_status,
                        "published_at": task_db.published_at,
                    }
                )
            else:
                _update(
                    {
                        "publish_provider": publish_provider,
                        "publish_key": publish_key,
                        "publish_url": publish_url,
                        "publish_status": "done" if publish_key else "failed",
                    }
                )
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.publish.done",
                message="Publish bundle build done",
                extra={"publish_key": publish_key},
            )
            logger.info(
                "APOLLO_AVATAR_BUILD_PUBLISH_BUNDLE_DONE",
                extra={"task_id": task_id, "publish_key": publish_key},
            )
        except Exception as exc:
            _append_event(
                repo,
                task_id,
                channel="apollo_avatar",
                code="post.error",
                message="Publish bundle failed",
                extra={"stage": "publish_bundle"},
            )
            logger.exception("Post-generate publish bundle failed", extra={"task_id": task_id})
            _update({"publish_status": "failed", "publish_error": str(exc)})
            # non-blocking for apollo_avatar
            if not is_apollo:
                return
        finally:
            db.close()
    else:
        logger.info("Post-generate: publish bundle already ready; skip", extra={"task_id": task_id})

    task = repo.get(task_id) or task
    if is_apollo:
        cur_status = str(task.get("status") or "").lower()
        pack_status = str(task.get("pack_status") or "").lower()
        pub_status = str(task.get("publish_status") or "").lower()
        if cur_status not in ("failed", "error"):
            updates = {}
            if pack_status not in ("failed", "error"):
                updates["pack_status"] = "ready"
            if pub_status not in ("failed", "error"):
                updates["publish_status"] = "ready"
            if updates:
                updates["status"] = "ready"
                task = policy_upsert(
                    repo,
                    task_id,
                    task,
                    updates,
                    step="steps_v1.post_pipeline",
                    force=force,
                )
            task = repo.get(task_id) or task
    pack_key = task.get("pack_key") or task.get("pack_path")
    if pack_key:
        if is_apollo:
            _update(
                {
                    "status": "ready",
                    "last_step": "publish" if task.get("publish_key") else "pack",
                    "error_message": None,
                    "error_reason": None,
                }
            )
        else:
            _update(
                {
                    "status": "done",
                    "last_step": "publish" if task.get("publish_key") else "pack",
                    "error_message": None,
                    "error_reason": None,
                }
            )
    if str(task.get("publish_status") or "").lower() == "ready":
        if not is_apollo:
            _update({"publish_status": "done"})

    _append_event(
        repo,
        task_id,
        channel="apollo_avatar",
        code="post.done",
        message="Post pipeline done",
        extra={
            "subtitles_status": task.get("subtitles_status"),
            "dub_status": task.get("dub_status"),
            "pack_status": task.get("pack_status"),
            "scenes_status": task.get("scenes_status"),
            "publish_status": task.get("publish_status"),
        },
    )
    logger.info("Post-generate pipeline done", extra={"task_id": task_id})


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


def _update_pipeline_config(task_id: str, updates: dict[str, str]) -> None:
    if not updates:
        return
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return
        current = parse_pipeline_config(task.pipeline_config)
        current.update(updates)
        task.pipeline_config = pipeline_config_to_storage(current)
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


