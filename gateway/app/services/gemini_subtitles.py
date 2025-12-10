from __future__ import annotations

import json
import logging

from fastapi import HTTPException

from gateway.app.providers.gemini_client import GeminiClientError, generate_text

logger = logging.getLogger(__name__)


def _decode_gemini_json(raw_text: str) -> dict:
    """Optionally decode JSON responses from Gemini."""

    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("Gemini subtitles response is empty")

    if not (raw_text.startswith("{") and "origin_srt" in raw_text):
        raise ValueError("Gemini subtitles response does not look like JSON")

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        logger.error(
            "Gemini subtitles raw_text is not valid JSON, first 200 chars: %r",
            raw_text[:200],
        )
        raise ValueError("Gemini subtitles response is not valid JSON") from exc


async def transcribe_and_translate_with_gemini(
    origin_srt: str, target_lang: str = "my"
) -> tuple[str, str]:
    """Translate an existing SRT to Burmese using Gemini."""

    prompt = f"""
You are a professional subtitle translator.

Input is a subtitle file in SRT format (index + timestamp + text) in Chinese.
Please translate ONLY the subtitle text into Burmese (language code "my"),
but keep the indices and timestamps exactly the same.

Output requirements:
- Output valid SRT format.
- Do NOT add explanations.
- Do NOT wrap the result in markdown or code fences.

Return either a valid SRT string in Burmese or a JSON object with keys
"origin_srt" and "mm_srt" containing the original and translated SRT.

Here is the original SRT:

{origin_srt}
"""

    try:
        mm_srt = await generate_text(prompt, temperature=0.2, max_output_tokens=4096)
    except GeminiClientError as exc:
        logger.error("Gemini subtitles failed: %s", exc)
        raise HTTPException(status_code=502, detail="Gemini subtitles failed") from exc

    mm_srt = (mm_srt or "").strip()
    if mm_srt.startswith("```"):
        parts = mm_srt.split("```")
        if len(parts) >= 3:
            mm_srt = parts[1]
        mm_srt = mm_srt.strip()

    origin_result = origin_srt
    mm_result = mm_srt

    if mm_result.startswith("{") and "origin_srt" in mm_result:
        try:
            parsed = _decode_gemini_json(mm_result)
            origin_result = parsed.get("origin_srt", origin_result) or origin_result
            mm_result = parsed.get("mm_srt", mm_result) or mm_result
        except ValueError as exc:  # pragma: no cover - defensive
            logger.error("Gemini subtitles JSON decode failed: %s", exc)
            raise HTTPException(
                status_code=502, detail="Gemini subtitles response is not valid JSON"
            ) from exc

    if not mm_result:
        raise HTTPException(status_code=502, detail="Gemini subtitles returned empty result")

    return origin_result, mm_result
