from __future__ import annotations

import logging

from gateway.app.providers.gemini_client import GeminiClientError, generate_text

logger = logging.getLogger(__name__)


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

Here is the original SRT:

{origin_srt}
"""

    try:
        mm_srt = await generate_text(prompt, temperature=0.2, max_output_tokens=4096)
    except GeminiClientError as exc:
        logger.error("Gemini subtitles failed: %s", exc)
        raise

    mm_srt = mm_srt.strip()
    if mm_srt.startswith("```"):
        parts = mm_srt.split("```")
        if len(parts) >= 3:
            mm_srt = parts[1]
        mm_srt = mm_srt.strip()

    if not mm_srt:
        raise GeminiClientError("Gemini subtitles returned empty result")

    return origin_srt, mm_srt
