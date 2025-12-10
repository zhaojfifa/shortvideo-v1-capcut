from __future__ import annotations

from pathlib import Path
import json
import logging
from typing import Tuple

import google.generativeai as genai

from gateway.app.config import get_settings


logger = logging.getLogger(__name__)


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


def _decode_gemini_json(raw_text: str) -> dict:
    """
    把 Gemini 返回的文本里真正的 JSON 抠出来再解析。

    处理几种常见情况：
    1. 返回被包在 ```json ... ``` 代码块里；
    2. 前后有解释性文字，只在中间一段是 JSON；
    3. JSON 前后有空行 / 空格。

    如果最终还是解析不了，会抛 ValueError，并在日志里打印前 200 字。
    """
    if raw_text is None:
        raise ValueError("Gemini subtitles response is empty")

    text = raw_text.strip()

    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.error(
            "Gemini subtitles raw_text 无法提取 JSON，前 200 字: %s",
            text[:200].replace("\n", " "),
        )
        raise ValueError("Gemini subtitles response is not valid JSON")

    json_str = text[start : end + 1]
    logger.info(
        "Gemini subtitles JSON 片段预览（前 400 字）: %s",
        json_str[:400].replace("\n", " "),
    )
    return json.loads(json_str)


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
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )

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

    raw_text = getattr(response, "text", None)
    if not raw_text:
        try:
            raw_text = response.candidates[0].content.parts[0].text
        except Exception:  # noqa: BLE001
            logger.error(
                "Gemini subtitles: 无法从 response 中提取文本，response=%r", response
            )
            raise

    logger.info(
        "Gemini subtitles raw_text 预览（前 500 字）: %s",
        str(raw_text)[:500].replace("\n", " "),
    )

    data = _decode_gemini_json(_ensure_no_markdown_fence(raw_text))

    origin_srt = data.get("origin_srt", "").strip()
    target_srt = data.get("target_srt", "").strip()

    if not origin_srt:
        raise RuntimeError("Gemini returned empty origin_srt")
    if not target_srt:
        raise RuntimeError("Gemini returned empty target_srt")

    return origin_srt, target_srt
