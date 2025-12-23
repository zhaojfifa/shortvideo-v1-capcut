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
GEMINI_MAX_OUTPUT_TOKENS = 8192
GEMINI_TEMPERATURE = 0.2
GEMINI_CANDIDATE_COUNT = 1


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


def _apply_generation_config(gen_cfg: Dict[str, Any]) -> None:
    gen_cfg.setdefault("responseMimeType", "application/json")
    gen_cfg.setdefault("maxOutputTokens", GEMINI_MAX_OUTPUT_TOKENS)
    gen_cfg.setdefault("temperature", GEMINI_TEMPERATURE)
    gen_cfg.setdefault("candidateCount", GEMINI_CANDIDATE_COUNT)


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
        "generationConfig": {},
    }
    _apply_generation_config(payload["generationConfig"])
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

    resp_json = resp.json()  # type: ignore[no-any-return]
    _log_finish_reasons(resp_json)
    return resp_json


def _call_gemini_with_payload(
    payload: Dict[str, Any],
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    通用的 Gemini 调用封装，主要用于多模态（视频）场景。
    """
    url = _build_gemini_url()
    params = {"key": GEMINI_API_KEY}

    gen_cfg = payload.setdefault("generationConfig", {})
    _apply_generation_config(gen_cfg)

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

    resp_json = resp.json()  # type: ignore[no-any-return]
    _log_finish_reasons(resp_json)
    return resp_json


def _extract_text(resp_json: Dict[str, Any]) -> str:
    """
    从 Gemini JSON 响应里把所有 text part 拼出来。
    v1beta 结构：candidates[*].content.parts[*].text
    """
    candidates: List[Dict[str, Any]] = resp_json.get("candidates") or []
    if not candidates:
        raise GeminiSubtitlesError("Gemini response has no candidates")

    def _texts_from_candidate(cand: Dict[str, Any]) -> List[str]:
        content: Dict[str, Any] = cand.get("content") or {}
        parts: List[Dict[str, Any]] = content.get("parts") or []
        out: List[str] = []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                out.append(part.get("text", "") or "")
        return out

    finish = candidates[0].get("finishReason")
    if finish:
        logger.info("Gemini finishReason=%s", finish)

    texts = _texts_from_candidate(candidates[0])
    if not texts:
        for cand in candidates[1:]:
            texts = _texts_from_candidate(cand)
            if texts:
                break

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

    raw = (raw or "").strip()
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        raw = (fenced_match.group(1) or "").strip()

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON block found in Gemini response")

    in_str = False
    esc = False
    depth = 0
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1].strip()

    raise ValueError("No complete JSON object found in Gemini response")

Input:
{raw_text}
""".strip()
    resp_json = _call_gemini(prompt)
    return _extract_text(resp_json)


def _repair_json_with_gemini(broken: str, timeout: int = 60) -> str:
    repair_prompt = (
        "You are a JSON repair tool. Fix the following broken JSON into a valid JSON object. "
        "Output ONLY the JSON object. No markdown, no code fences, no commentary."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": repair_prompt + "\n\n" + (broken or "")}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 4096,
            "temperature": 0,
            "candidateCount": 1,
        },
    }
    resp_json = _call_gemini_with_payload(payload, timeout=timeout)
    return _extract_text(resp_json)


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
        try:
            repaired_raw = _repair_json_with_gemini(payload_text)
            repaired_block = extract_json_block(repaired_raw)
            repaired_sanitized = sanitize_string_literals(repaired_block)
            try:
                return json.loads(repaired_block)
            except json.JSONDecodeError:
                return json.loads(repaired_sanitized)
        except Exception:
            logger.warning("Gemini subtitles did not return valid JSON. Snippet: %s", snippet)
            raise ValueError(f"Gemini subtitles did not return valid JSON. Snippet: {snippet}")



diff --git a/gateway/app/providers/gemini_subtitles.py b/gateway/app/providers/gemini_subtitles.py
index 1111111..2222222 100644
--- a/gateway/app/providers/gemini_subtitles.py
+++ b/gateway/app/providers/gemini_subtitles.py
@@ -1,20 +1,16 @@
 def translate_and_segment_with_gemini(
     origin_srt_text: str,
     target_lang: str = "my",
 ) -> Dict[str, Any]:
-    """
-    使用 Gemini 把 SRT 字幕翻译成缅甸语，并做场景分段。
-
-    返回结构：
-    {
-      "language": "<source_language_code>",
-      "segments": [...],
-      "scenes": [...]
-    }
-    """
+    # Use Gemini to translate SRT subtitles to Burmese and provide scene segmentation.
+    # Expected return schema:
+    # {
+    #   "language": "<source_language_code>",
+    #   "segments": [...],
+    #   "scenes": [...]
+    # }
     prompt = f"""
 You are a subtitle translator and scene segmenter for short social videos.



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
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "video/mp4",
                            "data": encoded,
                        }
                    },
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
