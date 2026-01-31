from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def probe_subtitles(video_path: Path) -> dict[str, Any]:
    if not video_path.exists():
        return {
            "status": "missing",
            "has_subtitle_stream": None,
            "subtitle_codecs": [],
            "subtitle_track_kind": "unknown",
        }

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {
            "status": "ffprobe_missing",
            "has_subtitle_stream": None,
            "subtitle_codecs": [],
            "subtitle_track_kind": "unknown",
        }

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(video_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        return {
            "status": "ffprobe_failed",
            "has_subtitle_stream": None,
            "subtitle_codecs": [],
            "subtitle_track_kind": "unknown",
        }

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "status": "ffprobe_bad_json",
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
    track_kind = "soft" if has_subtitle_stream else "hard"

    return {
        "status": "ok",
        "has_subtitle_stream": has_subtitle_stream,
        "subtitle_codecs": subtitle_codecs,
        "subtitle_track_kind": track_kind,
    }
