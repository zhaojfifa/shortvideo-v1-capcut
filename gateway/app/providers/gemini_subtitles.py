import base64
import json
import logging
import os
import re
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

# 配置项：优先使用 GEMINI_API_KEY，兼容 GOOGLE_API_KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class GeminiSubtitlesError(RuntimeError):
    """Raised when Gemini subtitles pipeline fails."""


def _build_gemini_url() -> str:
    """
    Build full Gemini REST URL, e.g.
    https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
    """
    if not GEMINI_API_KEY:
        raise GeminiSubtitlesError("GEMINI_API_KEY is not configured")

    base = GEMINI_BASE_URL.rstrip("/")
    return f"{base}/models/{GEMINI_MODEL}:generateContent"


def _call_gemini(prompt: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Call Gemini text model with a single text prompt and return raw JSON response.
    """
    url = _build_gemini_url()
    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                ],
            }
        ]
    }
    params = {"key": GEMINI_API_KEY}

    logger.info("Calling Gemini subtitles model %s", GEMINI_MODEL)
    resp = requests.post(url, params=params, json=payload, timeout=timeout)

    logger.info(
        "Gemini HTTP %s, body preview=%r",
        resp.status_code,
        resp.text[:300],
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:  # type: ignore[no-untyped-call]
        # 输出部分 body，方便在 Render 日志里排查 4xx/5xx
        logger.error("Gemini error body: %s", resp.text[:1000])
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}") from exc

    return resp.json()  # type: ignore[no-any-return]


def _call_gemini_with_payload(
    payload: Dict[str, Any],
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    通用的 Gemini 调用封装，主要用于多模态（视频）场景。
    """
    url = _build_gemini_url()
    params = {"key": GEMINI_API_KEY}

    logger.info("Calling Gemini subtitles model %s", GEMINI_MODEL)
    resp = requests.post(url, params=params, json=payload, timeout=timeout)

    logger.info(
        "Gemini HTTP %s, body preview=%r",
        resp.status_code,
        resp.text[:300],
    )

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:  # type: ignore[no-untyped-call]
        logger.error("Gemini error body: %s", resp.text[:1000])
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}") from exc

    return resp.json()  # type: ignore[no-any-return]


def _extract_text(resp_json: Dict[str, Any]) -> str:
    """
    从 Gemini JSON 响应里把所有 text part 拼出来。
    v1beta 结构：candidates[0].content.parts[*].text
    """
    candidates: List[Dict[str, Any]] = resp_json.get("candidates") or []
    if not candidates:
        raise GeminiSubtitlesError("Gemini response has no candidates")

    content: Dict[str, Any] = candidates[0].get("content") or {}
    parts: List[Dict[str, Any]] = content.get("parts") or []

    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
    if not texts:
        raise GeminiSubtitlesError("Gemini response has no text parts")

    return "".join(texts)


def _strip_code_fences(text: str) -> str:
    """
    去掉 ```json ... ``` 或 ``` ... ``` 这样的 code fence。
    """
    t = text.strip()

    if t.startswith("```"):
        # 去掉前导 ```
        t = t[3:]
        t = t.lstrip()

        lower = t.lower()
        if lower.startswith("json"):
            t = t[4:].lstrip()

        if t.endswith("```"):
            t = t[:-3].rstrip()

    return t


def _decode_gemini_json(raw_text: str) -> Dict[str, Any]:
    """
    Decode Gemini response text into JSON dict:
    - strip ``` / ```json fences
    - first try direct json.loads
    - then, if needed, extract the first {...} block and try again
    - on failure, log a snippet and raise GeminiSubtitlesError
    """
    cleaned = _strip_code_fences(raw_text)

    # 1) direct parse
    try:
        return json.loads(cleaned)
    except JSONDecodeError as exc1:
        # 2) try to parse only the first JSON object in the text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            snippet = match.group(0)
            try:
                return json.loads(snippet)
            except JSONDecodeError as exc2:
                logger.warning(
                    "Second JSON parse attempt for Gemini subtitles failed: %s; snippet head=%r",
                    exc2,
                    snippet[:200],
                )

        # 3) give up, log and raise
        logger.exception(
            "Gemini subtitles raw_text is not valid JSON. First 400 chars: %r",
            cleaned[:400],
        )
        raise GeminiSubtitlesError(
            "Gemini subtitles did not return valid JSON"
        ) from exc1


def translate_and_segment_with_gemini(
    origin_srt_text: str,
    target_lang: str = "my",
) -> Dict[str, Any]:
    """
    使用 Gemini 把 SRT 字幕翻译成缅甸语，并做场景分段。

    返回结构：
    {
      "language": "<source_language_code>",
      "segments": [...],
      "scenes": [...]
    }
    """
    prompt = f"""
You are a subtitle translator and scene segmenter for short social videos.

The input subtitles are in SRT format (original language).
Translate them to the target language "{target_lang}" (Burmese)
and also provide scene segmentation.

Return ONLY valid JSON with this exact shape:

{{
  "language": "<source_language_code>",
  "segments": [
    {{
      "index": 1,
      "start": 0.0,
      "end": 2.5,
      "origin": "original text",
      "mm": "Burmese text",
      "scene_id": 1
    }}
  ],
  "scenes": [
    {{
      "scene_id": 1,
      "start": 0.0,
      "end": 5.0,
      "title": "concise original scene title",
      "mm_title": "Burmese title"
    }}
  ]
}}

Rules:
- Keep segments in original SRT order; timestamps are in seconds.
- Make timestamps monotonic and non-overlapping.
- Keep translations concise and natural.
- If unsure about a scene title, keep it short or leave it empty.
- Respond with JSON only. Do NOT add explanations, backticks, or code fences.

    Here are the subtitles to process (SRT):

{origin_srt_text}
""".strip()

    # 1) 调用 Gemini
    resp_json = _call_gemini(prompt)
    raw_text = _extract_text(resp_json)
    data = _decode_gemini_json(raw_text)

    # 3) 做一点点 schema 校验，避免后续逻辑踩坑
    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError(
            "Gemini subtitles JSON must contain 'segments' and 'scenes'"
        )

    return data


def transcribe_translate_and_segment_with_gemini(
    video_path: Path,
    target_lang: str = "my",
) -> Dict[str, Any]:
    """
    使用 Gemini 2.0 Flash 对原始视频做转写 + 翻译 + 场景切分。

    期望返回结构：
    {
      "origin_srt": "...",
      "mm_srt": "...",
      "segments": [...],
      "scenes": [...]
    }
    """
    if not video_path.exists():
        raise GeminiSubtitlesError(f"Raw video not found: {video_path}")

    # 注意：这里使用 inline_data，而不是 file_data.data
    encoded = base64.b64encode(video_path.read_bytes()).decode("ascii")

    prompt = f"""
You are a subtitle transcriber, translator, and scene segmenter for short social videos.

Tasks:
1) Transcribe the spoken Chinese in the provided MP4 video into SRT subtitles (origin_srt).
2) Translate the subtitles into Burmese (mm_srt).
3) Provide scene segmentation that aligns with the subtitles.

Return ONLY valid JSON with this shape:
{{
  "origin_srt": "<full SRT string in source language>",
  "mm_srt": "<full SRT string translated to {target_lang}>",
  "segments": [
    {{"index": 1, "start": 0.0, "end": 2.5, "origin": "text", "mm": "translation", "scene_id": 1}}
  ],
  "scenes": [
    {{"scene_id": 1, "start": 0.0, "end": 5.0, "title": "scene title", "mm_title": "translated title"}}
  ]
}}

Rules:
- Keep timestamps in seconds, monotonic, and aligned between origin/mm.
- Respond with JSON only. Do NOT add explanations or code fences.
""".strip()

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "video/mp4",
                            "data": encoded,
                        }
                    },
                    {"text": prompt},
                ],
            }
        ]
    }

    resp_json = _call_gemini_with_payload(payload)
    raw_text = _extract_text(resp_json)
    data = _decode_gemini_json(raw_text)

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError(
            "Gemini subtitles JSON must contain 'segments' and 'scenes'"
        )

    return data
