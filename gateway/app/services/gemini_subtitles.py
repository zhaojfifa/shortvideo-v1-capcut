from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Tuple

from gateway.app.config import get_settings
from gateway.app.providers import gemini_subtitles as gemini_provider


logger = logging.getLogger(__name__)


def _decode_gemini_json(resp_json: dict) -> dict:
    """
    Extract subtitles JSON payload from Gemini generateContent response.
    """

    try:
        text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Unexpected Gemini subtitles response format: %r", resp_json)
        raise ValueError("Gemini subtitles response format changed") from exc

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - runtime guard
        logger.error(
            "Gemini subtitles raw_text is not valid JSON, first 200 chars: %r",
            str(text)[:200],
        )
        raise ValueError("Gemini subtitles raw response is not valid JSON") from exc

    if "origin_srt" not in parsed or "mm_srt" not in parsed:
        logger.error(
            "Gemini subtitles parsed JSON missing required keys: %r", parsed
        )
        raise ValueError("Gemini subtitles JSON missing required keys")

    return parsed


def transcribe_and_translate_with_gemini(
    wav_path: Path, target_lang: str = "my"
) -> Tuple[str, str]:
    """
    使用 Gemini 2.0 Flash 进行转写 + 翻译。
    Return: (origin_srt, target_srt)
    """

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    with wav_path.open("rb") as f:
        audio_bytes = f.read()

    system_prompt = (
        "You are a subtitles assistant for short vertical videos.\n"
        "Given an audio clip, transcribe it in the original language and translate it to the target language.\n"
        f"Target language: {target_lang} (use Burmese).\n"
        "Return a strict JSON object with keys origin_srt and mm_srt.\n"
        "Use standard JSON (double quotes, no comments, no markdown)."
    )

    inline_audio = {
        "inlineData": {
            "mimeType": "audio/wav",
            "data": base64.b64encode(audio_bytes).decode("ascii"),
        }
    }

    resp_json = gemini_provider.call_gemini_subtitles(
        system_prompt, parts_extra=[inline_audio]
    )

    data = _decode_gemini_json(resp_json)

    origin_srt = data.get("origin_srt", "").strip()
    mm_srt = data.get("mm_srt", data.get("target_srt", "")).strip()

    if not origin_srt:
        raise RuntimeError("Gemini returned empty origin_srt")
    if not mm_srt:
        raise RuntimeError("Gemini returned empty mm_srt")

    return origin_srt, mm_srt
