# -*- coding: utf-8 -*-
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

# Prefer GEMINI_API_KEY, fallback to GOOGLE_API_KEY for compatibility
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class GeminiSubtitlesError(RuntimeError):
    """Raised when Gemini subtitles pipeline fails."""


def _build_gemini_url() -> str:
    if not GEMINI_API_KEY:
        raise GeminiSubtitlesError("GEMINI_API_KEY is not configured")
    base = GEMINI_BASE_URL.rstrip("/")
    return f"{base}/models/{GEMINI_MODEL}:generateContent"


def _call_gemini(prompt: str, timeout: int = 60) -> Dict[str, Any]:
    url = _build_gemini_url()
    payload: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "response_mime_type": "application/json",
        },
    }
    resp = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=timeout)
    logger.info("Gemini HTTP %s, body preview=%r", resp.status_code, (resp.text or "")[:300])

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Gemini error body: %s", (resp.text or "")[:1000])
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}: {(resp.text or '')[:200]}") from exc

    return resp.json()  # type: ignore[no-any-return]


def _call_gemini_with_payload(payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    url = _build_gemini_url()
    params = {"key": GEMINI_API_KEY}

    gen_cfg = payload.setdefault("generationConfig", {})
    gen_cfg.setdefault("responseMimeType", "application/json")
    gen_cfg.setdefault("response_mime_type", "application/json")

    resp = requests.post(url, params=params, json=payload, timeout=timeout)
    logger.info("Gemini HTTP %s, body preview=%r", resp.status_code, (resp.text or "")[:300])

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Gemini error body: %s", (resp.text or "")[:1000])
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}: {(resp.text or '')[:200]}") from exc

    return resp.json()  # type: ignore[no-any-return]


def _extract_text(resp_json: Dict[str, Any]) -> str:
    candidates: List[Dict[str, Any]] = resp_json.get("candidates") or []
    if not candidates:
        raise GeminiSubtitlesError("Gemini response has no candidates")

    def _texts(cand: Dict[str, Any]) -> List[str]:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        out: List[str] = []
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                out.append(part.get("text") or "")
        return out

    texts = _texts(candidates[0])
    if not texts:
        for cand in candidates[1:]:
            texts = _texts(cand)
            if texts:
                break

    if not texts:
        raise GeminiSubtitlesError("Gemini response has no text parts")
    return "".join(texts).strip()


def extract_json_block(raw: str) -> str:
    raw = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fenced:
        raw = (fenced.group(1) or "").strip()

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


def sanitize_string_literals(text: str) -> str:
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


def _repair_json_with_gemini(broken: str, timeout: int = 60) -> str:
    repair_prompt = (
        "You are a JSON repair tool. Fix the following broken JSON into a valid JSON object. "
        "Output ONLY the JSON object. No markdown, no code fences, no commentary."
    )
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": repair_prompt + "\n\n" + (broken or "")}]}
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
    snippet = (raw_text or "")[:500].replace("\n", "\\n")
    text = (raw_text or "").strip()

    try:
        payload_text = extract_json_block(text)
    except ValueError:
        payload_text = text

    payload_sanitized = sanitize_string_literals(payload_text)

    # Strategy 1: strict JSON
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        try:
            return json.loads(payload_sanitized)
        except json.JSONDecodeError:
            pass

    # Strategy 2: python literal eval (fallback)
    try:
        data = ast.literal_eval(payload_sanitized)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Strategy 3: heuristic single-quote fix
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
        # Strategy 4: ask Gemini to repair
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


def translate_and_segment_with_gemini(origin_srt_text: str, target_lang: str = "my") -> Dict[str, Any]:
    prompt = f"""
You are a subtitle translator and scene segmenter for short social videos.

The input subtitles are in SRT format (original language).
Translate them to the target language "{target_lang}" (Burmese) and also provide scene segmentation.

Return ONLY valid JSON with this exact shape:
{{
  "language": "<source_language_code>",
  "segments": [
    {{"index": 1, "start": 0.0, "end": 2.5, "origin": "original text", "mm": "Burmese text", "scene_id": 1}}
  ],
  "scenes": [
    {{"scene_id": 1, "start": 0.0, "end": 5.0, "title": "concise original scene title", "mm_title": "Burmese title"}}
  ]
}}

Rules:
- Keep segments in original SRT order; timestamps are in seconds.
- Make timestamps monotonic and non-overlapping.
- All property names must be in double quotes; response must be strict JSON.
- Respond with JSON only. Do NOT add explanations or code fences.

Here are the subtitles to process (SRT):

{origin_srt_text}
""".strip()

    resp_json = _call_gemini(prompt)
    raw_text = _extract_text(resp_json)
    data = parse_gemini_subtitle_payload(raw_text)

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError("Gemini subtitles JSON must contain 'segments' and 'scenes'")

    return data


def transcribe_translate_and_segment_with_gemini(video_path: Path, target_lang: str = "my") -> Dict[str, Any]:
    if not video_path.exists():
        raise GeminiSubtitlesError(f"Raw video not found: {video_path}")

    encoded = base64.b64encode(video_path.read_bytes()).decode("ascii")

    prompt = f"""
You are a subtitle transcriber, translator, and scene segmenter for short social videos.

Tasks:
1) Transcribe the spoken Chinese in the provided MP4 video into subtitles.
2) Translate the subtitles into Burmese (target "{target_lang}").
3) Provide scene segmentation aligned with subtitles.

Return ONLY valid JSON with this shape:
{{
  "language": "<source_language_code>",
  "segments": [{{"index": 1, "start": 0.0, "end": 2.5, "origin": "Chinese text", "mm": "Burmese text", "scene_id": 1}}],
  "scenes": [{{"scene_id": 1, "start": 0.0, "end": 5.0, "title": "concise original scene title", "mm_title": "Burmese title"}}]
}}

Rules:
- Timestamps are seconds, monotonic, non-overlapping.
- All property names must be double-quoted.
- Respond with JSON only. No code fences.
""".strip()

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "video/mp4", "data": encoded}},
                ],
            }
        ]
    }

    resp_json = _call_gemini_with_payload(payload)
    raw_text = _extract_text(resp_json)
    data = parse_gemini_subtitle_payload(raw_text)

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

    if "segments" not in data or "scenes" not in data:
        raise GeminiSubtitlesError("Gemini subtitles JSON must contain 'segments' and 'scenes'")

    return data
