# gateway/app/providers/gemini_subtitles.py
import json
import logging
import os
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
    Call Gemini text model with a single text prompt and return parsed JSON response.
    """
    url = _build_gemini_url()
    payload: Dict[str, Any] = {
        "contents": [
            {
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
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}") from exc

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
        t = t.lstrip("`")

        # 可能是 "json" / "JSON"
        lower = t.lower()
        if lower.startswith("json"):
            t = t[4:]

        t = t.strip()

        if t.endswith("```"):
            t = t[:-3].strip()

    return t


def translate_and_segment_with_gemini(
    origin_srt_text: str,
    target_lang: str = "my",
) -> Dict[str, Any]:
    """
    使用 Gemini 把 SRT 字幕翻译成缅甸语，并做场景分段。

    返回结构：
    {
      "language": "<source_language_code>",
      "segments": [
        {"index": 1, "start": 0.0, "end": 2.5,
         "origin": "original text", "mm": "Burmese text", "scene_id": 1}
      ],
      "scenes": [
        {"scene_id": 1, "start": 0.0, "end": 5.0,
         "title": "concise original scene title", "mm_title": "Burmese title"}
      ]
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
    cleaned = _strip_code_fences(raw_text)

    # 2) 尝试解析 JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.exception(
            "Gemini subtitles raw_text is not valid JSON. First 400 chars: %r",
            cleaned[:400],
        )
        raise GeminiSubtitlesError(
            "Gemini subtitles did not return valid JSON"
        ) from exc

    # 3) 做一点点 schema 校验，避免后续逻辑踩坑
    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError(
            "Gemini subtitles JSON must contain 'segments' and 'scenes'"
        )

    return data
