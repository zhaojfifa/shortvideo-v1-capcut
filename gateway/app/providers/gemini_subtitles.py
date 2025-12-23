import ast
import base64
import json
import logging
import os
import re
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
        ],
        "generationConfig": {
            # Ask Gemini to respond with strict JSON
            "response_mime_type": "application/json",
        },
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

    # Ensure we always request JSON output from the model
    gen_cfg = payload.setdefault("generationConfig", {})
    if "response_mime_type" not in gen_cfg:
        gen_cfg["response_mime_type"] = "application/json"

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
    v1beta 结构：candidates[*].content.parts[*].text
    """
    candidates: List[Dict[str, Any]] = resp_json.get("candidates") or []
    if not candidates:
        raise GeminiSubtitlesError("Gemini response has no candidates")

    texts: List[str] = []
    for cand in candidates:
        content: Dict[str, Any] = cand.get("content") or {}
        parts: List[Dict[str, Any]] = content.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                texts.append(part.get("text", ""))

    if not texts:
        raise GeminiSubtitlesError("Gemini response has no text parts")

    return "".join(texts).strip()


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


def extract_json_block(raw: str) -> str:
    """
    Extract the most relevant JSON block from Gemini responses.

    - If a ```json ... ``` fenced block exists, return its inner content.
    - Otherwise, return the substring between the first '{' and the last '}'.
    - Raise ValueError if no JSON block is found.
    """

    raw = raw.strip()

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return fenced_match.group(1)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]

    raise ValueError("No JSON block found in Gemini response")

def sanitize_string_literals(text: str) -> str:
    """
    Make JSON-like text parseable by escaping raw control characters that appear
    inside quoted string literals.

    - Converts raw LF/CR/TAB inside strings to \\n/\\r/\\t
    - Converts other control chars (<0x20) inside strings to \\u00XX
    - Supports both "..." and '...' string delimiters (for heuristic/fallback paths)
    """
    if not text:
        return text

    out: list[str] = []
    in_string = False
    quote_char = ""
    escape = False

    for ch in text:
        if not in_string:
            if ch in ('"', "'"):
                in_string = True
                quote_char = ch
                escape = False
                out.append(ch)
            else:
                out.append(ch)
            continue

        # in_string == True
        if escape:
            out.append(ch)
            escape = False
            continue

        if ch == "\\":
            out.append(ch)
            escape = True
            continue

        if ch == quote_char:
            out.append(ch)
            in_string = False
            quote_char = ""
            continue

        if ch == "\n":
            out.append("\\n")
            continue
        if ch == "\r":
            out.append("\\r")
            continue
        if ch == "\t":
            out.append("\\t")
            continue

        oc = ord(ch)
        if oc < 0x20:
            out.append(f"\\u{oc:04x}")
            continue

        out.append(ch)

    return "".join(out)

def sanitize_string_literals(text: str) -> str:
    out: list[str] = []
    in_string = False
    quote_char = ""
    escape = False
    for ch in text:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == quote_char:
                out.append(ch)
                in_string = False
                quote_char = ""
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue
        if ch in {"'", '"'}:
            in_string = True
            quote_char = ch
            out.append(ch)
            continue
        out.append(ch)
    return "".join(out)


def parse_gemini_subtitle_payload(raw_text: str) -> Any:
    """
    Fault-tolerant parser for Gemini subtitle outputs.

    Attempts strict JSON first, then Python literal parsing, then a heuristic
    fix for single-quoted keys/values before failing with a descriptive error.
    """

    snippet = (raw_text or "")[:500].replace("\n", "\\n")
    text = (raw_text or "").strip()

    try:
        payload_text = extract_json_block(text)
    except ValueError:
        payload_text = text
    payload_sanitized = sanitize_string_literals(payload_text)

    # IMPORTANT: sanitize raw control chars INSIDE string literals
    payload_sanitized = sanitize_string_literals(payload_text)

    # Strategy 1: strict JSON (try original first, then sanitized)
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        try:
            return json.loads(payload_sanitized)
        except json.JSONDecodeError:
            pass

    try:
        data = ast.literal_eval(payload_sanitized)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Strategy 3: heuristic fix for single-quoted keys/values (apply on sanitized text)
    fixed = re.sub(
        r"(?P<q>')(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)'(?=\s*:)",
        r'"\g<key>"',
        payload_sanitized,
    )
    fixed = re.sub(
        r"':\s*'([^']*)'",
        lambda m: '": "{}"'.format(m.group(1).replace('"', '\\"')),
        fixed,
    )
    fixed = sanitize_string_literals(fixed)
    try:
        return json.loads(fixed)
    except Exception:
        logger.warning("Gemini subtitles did not return valid JSON. Snippet: %s", snippet)
        raise ValueError(f"Gemini subtitles did not return valid JSON. Snippet: {snippet}")



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
- All property names must be in double quotes; response must be strict JSON.
- Do not include trailing commas or comments.
- The response must be valid JSON that Python json.loads can parse.
- Respond with JSON only. Do NOT add explanations, backticks, or code fences.

    Here are the subtitles to process (SRT):

{origin_srt_text}
""".strip()

    # 1) 调用 Gemini
    resp_json = _call_gemini(prompt)
    raw_text = _extract_text(resp_json)
    data = parse_gemini_subtitle_payload(raw_text)

    # 3) 做一点点 schema 校验，避免后续逻辑踩坑
    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

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

    返回结构与 translate_and_segment_with_gemini 对齐：
    {
      "language": "<source_language_code>",
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
1) Transcribe the spoken Chinese in the provided MP4 video into subtitles.
2) Translate the subtitles into Burmese.
3) Provide scene segmentation that aligns with the subtitles.

Return ONLY valid JSON with this shape:
{{
  "language": "<source_language_code>",
  "segments": [
    {{"index": 1, "start": 0.0, "end": 2.5, "origin": "Chinese text", "mm": "Burmese text", "scene_id": 1}}
  ],
  "scenes": [
    {{"scene_id": 1, "start": 0.0, "end": 5.0, "title": "concise original scene title", "mm_title": "Burmese title"}}
  ]
}}

Rules:
- Keep timestamps in seconds, monotonic, and aligned between origin/mm.
- All property names must be in double quotes; response must be strict JSON.
- Do not include trailing commas or comments.
- The response must be valid JSON that Python json.loads can parse.
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

    try:
        data = parse_gemini_subtitle_payload(raw_text)
    except ValueError as exc:
        logger.error("%s", exc)
        raise GeminiSubtitlesError(str(exc)) from exc

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError(
            "Gemini subtitles JSON must contain 'segments' and 'scenes'"
        )

    return data
