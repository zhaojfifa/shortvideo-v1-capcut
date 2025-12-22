from __future__ import annotations

import json
import logging
import re

from fastapi import HTTPException

from gateway.app.providers.gemini_client import GeminiClientError, generate_text

logger = logging.getLogger(__name__)

_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _extract_time_lines(srt_text: str) -> list[str]:
    blocks = [b for b in (srt_text or "").split("\n\n") if b.strip()]
    time_lines: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            if _SRT_TIME_RE.search(line):
                time_lines.append(line.strip())
                break
    return time_lines


def validate_srt_structure(origin_srt: str, mm_srt: str) -> bool:
    origin_times = _extract_time_lines(origin_srt)
    mm_times = _extract_time_lines(mm_srt)
    if not origin_times or len(origin_times) != len(mm_times):
        return False
    return all(o == m for o, m in zip(origin_times, mm_times))


async def _retry_with_structure(origin_srt: str, target_lang: str) -> str:
    time_lines = _extract_time_lines(origin_srt)
    structured = "\n".join(
        f"{idx + 1}\n{line}" for idx, line in enumerate(time_lines)
    )
    retry_prompt = f"""
You are a professional subtitle translator.

Translate the original subtitle text into Burmese (language code "my").
You MUST keep the index and timestamp lines EXACTLY as provided below.
Do NOT add any explanations or extra text. Output valid SRT only.

Only fill the subtitle text lines for each block below:

{structured}
"""

    try:
        return await generate_text(retry_prompt, temperature=0.1, max_output_tokens=4096)
    except GeminiClientError as exc:
        logger.error("Gemini subtitles retry failed: %s", exc)
        raise HTTPException(status_code=502, detail="Gemini subtitles retry failed") from exc


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
Translate ONLY the subtitle text into Burmese (language code "my").
Keep indices and timestamps EXACTLY the same.

Style requirements:
- Favor natural, spoken Burmese (paraphrase if needed).
- Keep sentences short and conversational.
- If there is no direct Burmese term, translate by meaning.
- Proper nouns may remain in Chinese or English.

Output requirements:
- Output valid SRT format only.
- Do NOT add explanations or extra text.
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

    if not validate_srt_structure(origin_result, mm_result):
        logger.warning("Gemini subtitles structure invalid; retrying once.")
        retry_result = (await _retry_with_structure(origin_result, target_lang)).strip()
        if retry_result.startswith("```"):
            parts = retry_result.split("```")
            if len(parts) >= 3:
                retry_result = parts[1]
            retry_result = retry_result.strip()
        if not validate_srt_structure(origin_result, retry_result):
            logger.error(
                "Gemini subtitles structure still invalid. raw=%r",
                retry_result[:200],
            )
            raise HTTPException(status_code=502, detail="Gemini subtitles structure invalid")
        mm_result = retry_result

    return origin_result, mm_result
