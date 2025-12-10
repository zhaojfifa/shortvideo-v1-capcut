"""Gemini-based translation and scene segmentation helpers."""

import json
import logging
from typing import Iterable

import httpx

from gateway.app.config import get_settings

logger = logging.getLogger(__name__)


def _normalize_model_name(model: str) -> str:
    if model.startswith("models/"):
        return model.split("models/", 1)[1]
    return model


def call_gemini_subtitles(prompt: str, parts_extra: Iterable[dict] | None = None) -> dict:
    """Call Gemini generateContent for subtitles and return the full JSON response."""

    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")

    base_url = (settings.gemini_base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    model_name = _normalize_model_name(settings.gemini_model or "gemini-2.0-flash")
    url = f"{base_url}/models/{model_name}:generateContent?key={settings.gemini_api_key}"

    parts = [{"text": prompt}]
    if parts_extra:
        parts.extend(parts_extra)

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "origin_srt": {"type": "string"},
                "mm_srt": {"type": "string"},
            },
            "required": ["origin_srt", "mm_srt"],
        },
    }

    resp = httpx.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    resp_json = resp.json()
    logger.info("Gemini subtitles call succeeded, usage: %s", resp_json.get("usageMetadata"))
    return resp_json


def translate_and_segment_with_gemini(origin_srt_text: str, target_lang: str = "my") -> dict:
    """
    Translate and segment subtitles using Gemini.

    Returns dict with keys:
      - language: detected source language
      - segments: list of {index, start, end, origin, mm, scene_id}
      - scenes: list of {scene_id, start, end, title, mm_title}
    """

    prompt = f"""
You are a subtitle translator and scene segmenter for short social videos.

Input subtitles are in SRT format (original language). Translate them to {target_lang} (Burmese) and also provide scene segmentation.

Return ONLY valid JSON with this shape:
{{
  "language": "<source_language_code>",
  "segments": [
    {{"index": 1, "start": 0.0, "end": 2.5, "origin": "<original text>", "mm": "<Burmese text>", "scene_id": 1}},
    ...
  ],
  "scenes": [
    {{"scene_id": 1, "start": 0.0, "end": 5.0, "title": "<concise original scene title>", "mm_title": "<Burmese title>"}},
    ...
  ]
}}

Rules:
- Keep SRT timing order; timestamps are in seconds.
- Make timestamps monotonic and non-overlapping.
- Keep translations concise and natural.
- If unsure about a scene title, leave it empty string.
- Respond with JSON only, no markdown or commentary.

Here is the SRT to process:
```srt
{origin_srt_text}
```
"""

    try:
        response_json = call_gemini_subtitles(prompt)
    except Exception as exc:  # pragma: no cover - external request guard
        logger.exception("Gemini translation call failed")
        raise

    text = ""
    try:
        text = response_json.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        snippet = (text or "")[:500]
        logger.exception("Gemini translation JSON parse failed: %s", snippet)
        raise
