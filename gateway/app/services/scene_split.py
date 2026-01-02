from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from gateway.app.core.workspace import raw_path, workspace_root
from gateway.app.db import SessionLocal, engine, ensure_task_extra_columns
from gateway.app import models
from gateway.app.ports.storage_provider import get_storage_service

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCENE_SEC = 3.0
DEFAULT_MAX_SCENE_SEC = 18.0
DEFAULT_SILENCE_GAP_SEC = 0.6
DEFAULT_CAPTIONS_GROUP = 4

SRT_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,\.]\d{3})"
)


@dataclass
class Segment:
    start: float
    end: float
    text: str
    gap_after: float | None


@dataclass
class SceneRange:
    start: float
    end: float


def _ffmpeg_path() -> str:
    ffmpeg = shutil.which("ffmpeg")  # type: ignore[name-defined]
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    return ffmpeg


def _run_ffmpeg(args: list[str]) -> None:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")


def _slice_video(src: Path, dst: Path, start: float, end: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-c",
        "copy",
        str(dst),
    ]
    _run_ffmpeg(cmd)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"video slice missing: {dst}")


def _slice_audio(src: Path, dst: Path, start: float, end: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dst),
    ]
    try:
        _run_ffmpeg(cmd)
    except RuntimeError:
        duration = max(end - start, 0.1)
        _generate_silence_audio(dst, duration)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"audio slice missing: {dst}")


def _generate_silence_audio(dst: Path, seconds: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-t",
        f"{seconds:.3f}",
        "-acodec",
        "pcm_s16le",
        str(dst),
    ]
    _run_ffmpeg(cmd)


def _transcribe_segments(audio_path: Path) -> list[Segment]:
    model_name = os.getenv("FASTER_WHISPER_MODEL", "base")
    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments_iter, _info = model.transcribe(str(audio_path), word_timestamps=True)
    segs = list(segments_iter)
    out: list[Segment] = []
    for idx, seg in enumerate(segs):
        text = (seg.text or "").strip()
        gap_after = None
        if idx + 1 < len(segs):
            next_seg = segs[idx + 1]
            if getattr(seg, "words", None) and getattr(next_seg, "words", None):
                last_word = seg.words[-1]
                next_first = next_seg.words[0]
                gap_after = float(next_first.start) - float(last_word.end)
        out.append(
            Segment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
                gap_after=gap_after,
            )
        )
    return out


def _derive_scenes_from_segments(
    segments: list[Segment],
    *,
    min_scene_sec: float,
    max_scene_sec: float,
    silence_gap_sec: float,
    captions_group: int,
) -> list[SceneRange]:
    if not segments:
        raise RuntimeError("no segments to derive scenes")

    scenes: list[SceneRange] = []
    scene_start = segments[0].start
    count_since_cut = 0
    last_end = segments[-1].end

    for idx, seg in enumerate(segments):
        count_since_cut += 1
        seg_end = seg.end
        next_start = segments[idx + 1].start if idx + 1 < len(segments) else None
        gap = seg.gap_after
        if gap is None and next_start is not None:
            gap = next_start - seg_end
        gap = gap or 0.0

        duration = seg_end - scene_start
        candidate = False
        if next_start is not None and gap >= silence_gap_sec:
            candidate = True
        if count_since_cut >= captions_group:
            candidate = True
        if duration >= max_scene_sec:
            candidate = True

        if candidate and duration >= min_scene_sec:
            scenes.append(SceneRange(start=scene_start, end=seg_end))
            scene_start = seg_end
            count_since_cut = 0

    if not scenes:
        scenes.append(SceneRange(start=segments[0].start, end=last_end))
        return scenes

    if scenes[-1].end < last_end:
        last_duration = last_end - scene_start
        if last_duration < min_scene_sec:
            scenes[-1] = SceneRange(start=scenes[-1].start, end=last_end)
        else:
            scenes.append(SceneRange(start=scene_start, end=last_end))

    return scenes


def _parse_srt(text: str) -> list[dict]:
    blocks = [b for b in text.strip().split("\n\n") if b.strip()]
    entries: list[dict] = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if lines[0].strip().isdigit() else lines[0]
        match = SRT_TIME_RE.search(time_line)
        if not match:
            continue
        start = _parse_srt_time(match.group("start"))
        end = _parse_srt_time(match.group("end"))
        text_lines = lines[2:] if lines[0].strip().isdigit() else lines[1:]
        entries.append({"start": start, "end": end, "text": "\n".join(text_lines)})
    return entries


def _parse_srt_time(value: str) -> float:
    h, m, rest = value.replace(",", ".").split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _format_srt_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    ms_total = int(round(seconds * 1000))
    ms = ms_total % 1000
    s_total = ms_total // 1000
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _clip_srt(entries: Iterable[dict], start: float, end: float) -> str:
    out_lines: list[str] = []
    idx = 1
    for entry in entries:
        e_start = float(entry["start"])
        e_end = float(entry["end"])
        if e_end <= start or e_start >= end:
            continue
        new_start = max(e_start, start) - start
        new_end = min(e_end, end) - start
        if new_end <= 0:
            continue
        out_lines.append(str(idx))
        out_lines.append(f"{_format_srt_time(new_start)} --> {_format_srt_time(new_end)}")
        out_lines.append(entry["text"].strip())
        out_lines.append("")
        idx += 1
    return "\n".join(out_lines).strip() + ("\n" if idx > 1 else "")


def _find_source_srt(task_id: str) -> tuple[Path, str]:
    base = workspace_root() / "deliver" / "packs" / task_id / "subs"
    mm = base / "mm.srt"
    origin = base / "origin.srt"
    if mm.exists():
        return mm, "mm"
    if origin.exists():
        return origin, "origin"
    raise RuntimeError("source subtitles not found under deliver/packs")


def _write_readme(dst: Path, rows: list[dict]) -> None:
    lines = [
        "# Scenes Package",
        "",
        "| Scene | Start | End | Duration | Subtitle Preview |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scene_id']} | {row['start']} | {row['end']} | {row['duration']} | {row['preview']} |"
        )
    lines.append("")
    dst.write_text("\n".join(lines), encoding="utf-8")


def generate_scenes_package(
    task_id: str,
    *,
    min_scene_sec: float = DEFAULT_MIN_SCENE_SEC,
    max_scene_sec: float = DEFAULT_MAX_SCENE_SEC,
    silence_gap_sec: float = DEFAULT_SILENCE_GAP_SEC,
    captions_group: int = DEFAULT_CAPTIONS_GROUP,
) -> dict:
    ensure_task_extra_columns(engine)
    raw = raw_path(task_id)
    if not raw.exists():
        raise RuntimeError("raw video not found")

    source_srt, source_lang = _find_source_srt(task_id)
    srt_entries = _parse_srt(source_srt.read_text(encoding="utf-8"))
    segments = _transcribe_segments(raw)
    scenes = _derive_scenes_from_segments(
        segments,
        min_scene_sec=min_scene_sec,
        max_scene_sec=max_scene_sec,
        silence_gap_sec=silence_gap_sec,
        captions_group=captions_group,
    )

    out_root = workspace_root() / "deliver" / "scenes" / task_id
    package_root = out_root / "scenes_package"
    scenes_root = package_root / "scenes"
    package_root.mkdir(parents=True, exist_ok=True)
    scenes_root.mkdir(parents=True, exist_ok=True)

    readme_rows: list[dict] = []
    manifest_scenes: list[dict] = []

    for idx, scene in enumerate(scenes, start=1):
        scene_id = f"scene_{idx:03d}"
        scene_dir = scenes_root / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        video_path = scene_dir / "video.mp4"
        audio_path = scene_dir / "audio.wav"
        subs_path = scene_dir / "subs.srt"
        scene_json_path = scene_dir / "scene.json"

        _slice_video(raw, video_path, scene.start, scene.end)
        _slice_audio(raw, audio_path, scene.start, scene.end)

        clipped_srt = _clip_srt(srt_entries, scene.start, scene.end)
        subs_path.write_text(clipped_srt, encoding="utf-8")

        preview = ""
        for entry in srt_entries:
            if entry["end"] > scene.start and entry["start"] < scene.end:
                preview = entry["text"].splitlines()[0].strip()
                break

        scene_payload = {
            "scene_id": scene_id,
            "source": {
                "task_id": task_id,
                "origin_video": str(raw),
                "time_range": [round(scene.start, 3), round(scene.end, 3)],
            },
            "semantics": {
                "role": "unknown",
                "language": source_lang,
                "summary": preview or f"{scene_id} clip",
            },
            "assets": {
                "video": "video.mp4",
                "audio": "audio.wav",
                "subs": "subs.srt",
            },
        }
        scene_json_path.write_text(
            json.dumps(scene_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        duration = scene.end - scene.start
        readme_rows.append(
            {
                "scene_id": scene_id,
                "start": f"{scene.start:.2f}s",
                "end": f"{scene.end:.2f}s",
                "duration": f"{duration:.2f}s",
                "preview": preview,
            }
        )
        manifest_scenes.append(
            {
                "scene_id": scene_id,
                "start": round(scene.start, 3),
                "end": round(scene.end, 3),
                "duration": round(duration, 3),
                "assets": {
                    "video": f"scenes/{scene_id}/video.mp4",
                    "audio": f"scenes/{scene_id}/audio.wav",
                    "subs": f"scenes/{scene_id}/subs.srt",
                    "scene_json": f"scenes/{scene_id}/scene.json",
                },
                "subtitle_preview": preview,
            }
        )

    manifest = {
        "version": "1.8",
        "task_id": task_id,
        "source_subtitles": source_lang,
        "scenes": manifest_scenes,
    }
    manifest_path = package_root / "scenes_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    readme_path = package_root / "README.md"
    _write_readme(readme_path, readme_rows)

    zip_path = out_root / "scenes.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for item in package_root.rglob("*"):
            if item.is_file():
                zf.write(item, arcname=item.relative_to(package_root).as_posix())

    storage = get_storage_service()
    scenes_key = f"deliver/scenes/{task_id}/scenes.zip"
    storage.upload_file(str(zip_path), scenes_key, content_type="application/zip")

    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            task.scenes_key = scenes_key
            task.scenes_status = "ready"
            task.scenes_count = len(manifest_scenes)
            db.commit()
    finally:
        db.close()

    return {
        "task_id": task_id,
        "scenes_key": scenes_key,
        "scenes_count": len(manifest_scenes),
        "zip_path": str(zip_path),
        "manifest_path": str(manifest_path),
    }
