from __future__ import annotations

from pathlib import Path
import json
from typing import Tuple

import google.generativeai as genai

from gateway.app.config import get_settings


def _ensure_no_markdown_fence(text: str) -> str:
    """
    有些大模型喜欢用 ```json 包一层，这里简单剥掉。
    """
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def transcribe_and_translate_with_gemini(
    wav_path: Path,
    target_lang: str = "my",
) -> Tuple[str, str]:
    """
    使用 Gemini 2.0 Flash 进行转写 + 翻译。
    Return: (origin_srt, target_srt)
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)

    with wav_path.open("rb") as f:
        audio_bytes = f.read()

    system_prompt = (
        "You are a subtitles assistant for short vertical videos.\n"
        "Given an audio clip in a single non-English language, you must:\n"
        "1) Transcribe the speech in the original language into standard SRT format.\n"
        f"2) Translate it into {target_lang} (Burmese) and also format it as standard SRT.\n"
        "Return a pure JSON object with two string fields:\n"
        '  { "origin_srt": "<SRT in source language>", "target_srt": "<SRT in target language>" }\n'
        "Do not include any explanations or comments.\n"
    )

    response = model.generate_content(
        [
            system_prompt,
            {
                "mime_type": "audio/wav",
                "data": audio_bytes,
            },
        ]
    )

    raw_text = _ensure_no_markdown_fence(response.text or "")
    data = json.loads(raw_text)

    origin_srt = data.get("origin_srt", "").strip()
    target_srt = data.get("target_srt", "").strip()

    if not origin_srt:
        raise RuntimeError("Gemini returned empty origin_srt")
    if not target_srt:
        raise RuntimeError("Gemini returned empty target_srt")

    return origin_srt, target_srt
