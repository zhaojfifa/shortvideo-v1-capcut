"""Gemini-based translation and scene segmentation helpers."""

import json
import logging

from gateway.app.providers.gemini_client import call_gemini

logger = logging.getLogger(__name__)


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
{
  "language": "<source_language_code>",
  "segments": [
    {"index": 1, "start": 0.0, "end": 2.5, "origin": "<original text>", "mm": "<Burmese text>", "scene_id": 1},
    ...
  ],
  "scenes": [
    {"scene_id": 1, "start": 0.0, "end": 5.0, "title": "<concise original scene title>", "mm_title": "<Burmese title>"},
    ...
  ]
}

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
        response_text = call_gemini(prompt)
    except Exception as exc:  # pragma: no cover - external request guard
        logger.exception("Gemini translation call failed")
        raise

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        snippet = response_text[:500]
        logger.exception("Gemini translation JSON parse failed: %s", snippet)
        raise
