from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


_EDGE_YAVG_RE = re.compile(r"YAVG:(?P<yavg>[0-9.]+)")


def _ffprobe_streams(video_path: Path) -> tuple[str, dict[str, Any] | None]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return "ffprobe_missing", None

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(video_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return "ffprobe_timeout", None
    if proc.returncode != 0:
        return "ffprobe_failed", None

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return "ffprobe_bad_json", None
    return "ok", payload


def _edge_density_yavg(video_path: Path, timestamp: str) -> float | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    vf = (
        "crop=iw:ih/3:0:ih*2/3,"
        "scale=320:-1,"
        "edgedetect=low=0.1:high=0.2,"
        "format=gray,"
        "signalstats"
    )
    cmd = [
        ffmpeg,
        "-ss",
        timestamp,
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-vf",
        vf,
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return None

    match = _EDGE_YAVG_RE.search(proc.stderr or "")
    if not match:
        return None
    try:
        return float(match.group("yavg"))
    except ValueError:
        return None


def _probe_burned_subtitles(video_path: Path) -> tuple[str, float | None]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "ffmpeg_missing", None

    samples = ["00:00:02.0", "00:00:05.0", "00:00:10.0"]
    values: list[float] = []
    for ts in samples:
        yavg = _edge_density_yavg(video_path, ts)
        if yavg is not None:
            values.append(yavg)

    if not values:
        return "ffmpeg_no_samples", None

    avg = sum(values) / len(values)
    return "ok", avg


def probe_subtitles(video_path: Path) -> dict[str, Any]:
    if not video_path.exists():
        return {
            "status": "missing",
            "has_subtitle_stream": None,
            "subtitle_codecs": [],
            "subtitle_track_kind": "unknown",
        }

    status, payload = _ffprobe_streams(video_path)
    if status != "ok" or payload is None:
        return {
            "status": status,
            "has_subtitle_stream": None,
            "subtitle_codecs": [],
            "subtitle_track_kind": "unknown",
        }

    streams = payload.get("streams", []) or []
    subtitle_codecs = [
        s.get("codec_name")
        for s in streams
        if s.get("codec_type") == "subtitle" and s.get("codec_name")
    ]
    has_subtitle_stream = bool(subtitle_codecs)
    if has_subtitle_stream:
        track_kind = "embedded"
        return {
            "status": "ok",
            "has_subtitle_stream": True,
            "subtitle_codecs": subtitle_codecs,
            "subtitle_track_kind": track_kind,
        }

    burn_status, edge_avg = _probe_burned_subtitles(video_path)
    if burn_status == "ok" and edge_avg is not None:
        track_kind = "burned" if edge_avg >= 12.0 else "none"
        status_out = "ok"
    elif burn_status in {"ffmpeg_missing", "ffmpeg_no_samples"}:
        track_kind = "unknown"
        status_out = burn_status
    else:
        track_kind = "unknown"
        status_out = "unknown"

    return {
        "status": status_out,
        "has_subtitle_stream": False,
        "subtitle_codecs": subtitle_codecs,
        "subtitle_track_kind": track_kind,
    }
