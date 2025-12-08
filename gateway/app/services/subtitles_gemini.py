import json
from pathlib import Path

from google import genai

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    origin_srt_path,
    raw_path,
    segments_json_path,
    subs_dir,
    translated_srt_path,
    workspace_root,
)
from gateway.app.services.subtitles import SubtitleError, preview_lines


def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SubtitleError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key, base_url=settings.gemini_base_url)


def _model(client: genai.Client):
    settings = get_settings()
    return client.models.get(settings.gemini_model)


def _format_timestamp(seconds: float) -> str:
    total_ms = int(float(seconds) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg.get("start", 0))
        end = _format_timestamp(seg.get("end", seg.get("start", 0)))
        text = str(seg.get("text", "")).strip()
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    return "\n".join(lines).strip() + "\n"


def _preview_text(path: Path) -> list[str]:
    return preview_lines(path.read_text(encoding="utf-8"))


async def generate_with_gemini(
    task_id: str,
    target_lang: str = "my",
    with_scenes: bool = True,
) -> dict:
    raw = raw_path(task_id)
    if not raw.exists():
        raise SubtitleError("raw video not found")

    client = _client()
    model = _model(client)

    file = client.files.upload(file=str(raw))
    file_uri = getattr(file, "uri", None)
    if not file_uri:
        raise SubtitleError("failed to upload file to Gemini")

    prompt = (
        "You are a transcription and scene segmentation engine.\n\n"
        "- Watch and listen to the attached short video.\n"
        "- Split it into natural scenes based on topic or visual changes.\n"
        "- Return a JSON object with key \"segments\".\n"
        "- Each segment:\n  {\n    \"scene_id\": <int starting from 1>,\n    \"start\": <float seconds>,\n    \"end\": <float seconds>,\n    \"text\": \"<original language transcript>\"\n  }\n"
        "- Timestamps must be strictly increasing and non-overlapping.\n"
        "- Use the original spoken language (do NOT translate).\n"
        "- Return ONLY JSON."
    )

    resp = model.generate_content(
        contents=[
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"file_data": {"file_uri": file_uri}},
                ],
            }
        ],
        config={"response_mime_type": "application/json"},
    )

    segments_obj = json.loads(getattr(resp, "text", "{}"))
    segments = segments_obj.get("segments", []) if isinstance(segments_obj, dict) else []

    subs_dir().mkdir(parents=True, exist_ok=True)
    origin_path = origin_srt_path(task_id)
    origin_srt_text = segments_to_srt(segments)
    origin_path.write_text(origin_srt_text, encoding="utf-8")

    scenes_path = segments_json_path(task_id)
    scenes_path.write_text(json.dumps(segments_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    translate_prompt = (
        "You are a subtitle translator.\n\n"
        "Input: SRT subtitles in the original language.\n"
        "Task:\n"
        "- Translate ONLY the subtitle text lines into Burmese (my).\n"
        "- Keep indices and timestamps EXACTLY the same.\n"
        "- Output valid SRT in UTF-8.\n\n"
        "Here is the SRT:\n\n"
        f"{origin_srt_text}"
    )

    translate_resp = model.generate_content(
        contents=[{"role": "user", "parts": [{"text": translate_prompt}]}]
    )
    mm_srt_text = getattr(translate_resp, "text", "") or ""
    suffix = "mm" if (target_lang or "").lower() in {"my", "mm"} else (target_lang or "mm")
    mm_srt_path = translated_srt_path(task_id, suffix)
    mm_srt_path.write_text(mm_srt_text, encoding="utf-8")

    return {
        "task_id": task_id,
        "origin_srt": str(origin_path.relative_to(workspace_root())),
        "mm_srt": str(mm_srt_path.relative_to(workspace_root())),
        "segments_json": str(scenes_path.relative_to(workspace_root())) if with_scenes else None,
        "wav": None,
        "origin_preview": _preview_text(origin_path),
        "mm_preview": _preview_text(mm_srt_path),
    }
