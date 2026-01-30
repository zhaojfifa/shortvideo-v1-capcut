import json
from pathlib import Path
from typing import Any

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    origin_srt_path,
    raw_input_path,
    segments_json_path,
    subs_dir,
    translated_srt_path,
    workspace_root,
)
from gateway.app.services.subtitles_openai import SubtitleError, preview_lines


def _format_timestamp(seconds: float) -> str:
    total_ms = int(float(seconds) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(segments: list[dict[str, Any]], text_key: str) -> str:
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg.get("start", 0))
        end = _format_timestamp(seg.get("end", seg.get("start", 0)))
        text = (
            str(seg.get(text_key) or seg.get("text") or seg.get("text_zh") or "")
            .strip()
        )
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    return "\n".join(lines).strip() + "\n"


def _preview_text(path: Path) -> list[str]:
    return preview_lines(path.read_text(encoding="utf-8"))


async def generate_with_gemini(
    task_id: str,
    target_lang: str = "my",
    with_scenes: bool = True,
) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SubtitleError("GEMINI_API_KEY is not configured")

    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - import guard
        raise SubtitleError("google-genai is not installed") from exc

    raw = raw_input_path(task_id)
    if not raw.exists():
        raise SubtitleError("raw video not found")

    client = genai.Client(api_key=settings.gemini_api_key)
    model = settings.gemini_model or "gemini-2.0-flash"

    prompt = (
        "You are a transcription and segmentation engine. Given a short social video, "
        "output JSON with an array 'segments', each having start (sec), end (sec), "
        "text_zh (original language transcript), and text_my (Burmese translation). "
        "Timestamps must be monotonic and contiguous."
    )

    try:
        with raw.open("rb") as f:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    {"mime_type": "video/mp4", "data": f.read()},
                ],
                config={"response_mime_type": "application/json"},
            )
    except Exception as exc:  # pragma: no cover - runtime guard
        raise SubtitleError(f"Gemini request failed: {exc}") from exc

    try:
        segments_obj = json.loads(getattr(resp, "text", "{}"))
    except json.JSONDecodeError as exc:
        raise SubtitleError(f"Gemini returned invalid JSON: {exc}") from exc

    if not isinstance(segments_obj, dict):
        raise SubtitleError("Gemini response is not a JSON object")

    segments = segments_obj.get("segments", []) if isinstance(segments_obj, dict) else []
    if not isinstance(segments, list):
        segments = []

    subs_dir(task_id).mkdir(parents=True, exist_ok=True)

    origin_path = origin_srt_path(task_id)
    mm_path = translated_srt_path(task_id, "mm")
    origin_srt_text = _segments_to_srt(segments, "text_zh")
    mm_srt_text = _segments_to_srt(segments, "text_my")
    if not mm_srt_text.strip():
        mm_srt_text = _segments_to_srt(segments, "text")

    origin_path.write_text(origin_srt_text, encoding="utf-8")
    mm_path.write_text(mm_srt_text, encoding="utf-8")

    scenes_path = segments_json_path(task_id)
    if with_scenes:
        scenes_path.write_text(
            json.dumps(segments_obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        scenes_path = None

    return {
        "task_id": task_id,
        "origin_srt": str(origin_path.relative_to(workspace_root())),
        "mm_srt": str(mm_path.relative_to(workspace_root())),
        "segments_json": str(scenes_path.relative_to(workspace_root())) if scenes_path else None,
        "wav": None,
        "origin_preview": _preview_text(origin_path),
        "mm_preview": _preview_text(mm_path),
    }
