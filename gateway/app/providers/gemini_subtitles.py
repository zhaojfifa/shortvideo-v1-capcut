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
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

# Prefer GEMINI_API_KEY, fallback to GOOGLE_API_KEY for compatibility
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_MAX_OUTPUT_TOKENS = 8192
GEMINI_TEMPERATURE = 0.2
GEMINI_CANDIDATE_COUNT = 1


class GeminiSubtitlesError(RuntimeError):
    """Raised when Gemini subtitles pipeline fails."""


def _build_gemini_url() -> str:
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
    url = _build_gemini_url()
    payload: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            "temperature": GEMINI_TEMPERATURE,
            "candidateCount": GEMINI_CANDIDATE_COUNT,
        },
    }
    resp = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=timeout)
    logger.info("Gemini HTTP %s, body preview=%r", resp.status_code, (resp.text or "")[:300])

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:  # type: ignore[no-untyped-call]
        logger.error("Gemini error body: %s", resp.text[:1000])
        raise GeminiSubtitlesError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}") from exc

    return resp.json()  # type: ignore[no-any-return]


def _call_gemini_with_payload(payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    url = _build_gemini_url()
    params = {"key": GEMINI_API_KEY}

    gen_cfg = payload.setdefault("generationConfig", {})
    gen_cfg.setdefault("responseMimeType", "application/json")
    gen_cfg.setdefault("maxOutputTokens", GEMINI_MAX_OUTPUT_TOKENS)
    gen_cfg.setdefault("temperature", GEMINI_TEMPERATURE)
    gen_cfg.setdefault("candidateCount", GEMINI_CANDIDATE_COUNT)

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


def _extract_json_payload(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start_candidates = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx != -1]
    start = min(start_candidates) if start_candidates else -1
    end_candidates = [idx for idx in (cleaned.rfind("}"), cleaned.rfind("]")) if idx != -1]
    end = max(end_candidates) if end_candidates else -1

    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()
    return cleaned.strip()


def _safe_json_loads(text: str) -> dict:
    payload = _extract_json_payload(text)
    payload = (
        payload.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    payload = re.sub(r"[\ufeff\u200b\u200c\u200d\u2060]", "", payload)
    payload = re.sub(r",\s*([}\]])", r"\1", payload)

    try:
        data = json.loads(payload)
    except Exception as exc:
        snippet = re.sub(r"\s+", " ", (text or "").strip())
        if len(snippet) > 800:
            snippet = snippet[:800] + "..."
        raise GeminiSubtitlesError(f"Gemini JSON parse failed: {snippet}") from exc

    if not isinstance(data, dict):
        snippet = re.sub(r"\s+", " ", (text or "").strip())
        if len(snippet) > 800:
            snippet = snippet[:800] + "..."
        raise GeminiSubtitlesError(f"Gemini JSON payload invalid: {snippet}")

    return data


def parse_gemini_json_payload(raw_text: str) -> dict:
    payload = _safe_json_loads(raw_text)
    if not isinstance(payload.get("segments"), list):
        snippet = re.sub(r"\s+", " ", (raw_text or "").strip())
        if len(snippet) > 800:
            snippet = snippet[:800] + "..."
        raise GeminiSubtitlesError(f"Gemini JSON payload invalid: {snippet}")
    return payload


def _ensure_scenes(data: dict) -> dict:
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise GeminiSubtitlesError("Gemini subtitles JSON must contain 'segments'")
    if not segments:
        raise GeminiSubtitlesError("Gemini subtitles returned empty segments")
    scenes = data.get("scenes")
    if isinstance(scenes, list):
        return data
    start = segments[0].get("start")
    end = segments[-1].get("end")
    data["scenes"] = [
        {"scene_id": 1, "start": start, "end": end, "title": "", "mm_title": ""}
    ]
    logger.info("Gemini subtitles missing scenes; synthesized fallback scene")
    return data


def extract_json_block(raw: str) -> str:
    """
    Extract the most relevant JSON object from Gemini responses.

    Strategy:
    - If a ```json ...``` (or ``` ... ```) fenced block exists, use its inner content.
    - Otherwise, return the substring from the first '{' to the matching final '}' (brace-balanced).
    - Raise ValueError if no complete JSON object is found.
    """
    raw = (raw or "").strip()

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        raw = (fenced_match.group(1) or "").strip()

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object start '{' found in Gemini response")

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
    """
    Escape raw control characters that appear *inside* quoted string literals so the
    JSON-like payload becomes parseable.

    - Converts raw LF/CR/TAB inside strings to \\n/\\r/\\t
    - Converts other control chars (<0x20) inside strings to \\u00XX
    - Only operates while inside a quoted string (supports both " and ' for fallback parsing)
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

        # inside a quoted string
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

        # normalize control characters inside string literals
        if ch == "\n":
            out.append("\\n")
            continue
        if ch == "\r":
            out.append("\\r")
            continue
        if ch == "\t":
            out.append("\\t")
            continue

        code = ord(ch)
        if code < 0x20:
            out.append(f"\\u{code:04x}")
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
            {
                "role": "user",
                "parts": [{"text": repair_prompt + "\n\n" + (broken or "")}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "candidateCount": 1,
        },
    }
    resp_json = _call_gemini_with_payload(payload, timeout=timeout)
    return _extract_text(resp_json)


def _write_debug_text(debug_dir: Path | None, filename: str, text: str) -> None:
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / filename).write_text(text or "", encoding="utf-8")


def parse_gemini_subtitle_payload(
    raw_text: str,
    *,
    allow_repair: bool = True,
    debug_dir: Path | None = None,
    write_debug: bool = False,
) -> Any:
    text = (raw_text or "").strip()
    snippet = (text[:500]).replace("\n", "\\n")

    if write_debug:
        _write_debug_text(debug_dir, "gemini_response_raw.txt", text)

    # Extract best-effort JSON object text
    try:
        payload_text = extract_json_block(text)
    except Exception:
        payload_text = text

    payload_text = _TRAILING_COMMA_RE.sub(r"\1", payload_text)

    if allow_repair and ("..." in payload_text or "\u2026" in payload_text):
        try:
            repaired_raw = _repair_json_with_gemini(payload_text)
            payload_text = extract_json_block(repaired_raw)
            payload_text = _TRAILING_COMMA_RE.sub(r"\1", payload_text)
        except Exception:
            pass

    if write_debug:
        _write_debug_text(debug_dir, "gemini_response_json_block.txt", payload_text)

    # Sanitize control chars inside quoted string literals (best-effort)
    try:
        payload_sanitized = sanitize_string_literals(payload_text)
    except Exception:
        payload_sanitized = payload_text

    if write_debug:
        _write_debug_text(debug_dir, "gemini_payload_sanitized.txt", payload_sanitized)

    # 1) Prefer sanitized strict JSON parse (highest hit-rate in practice)
    try:
        return parse_gemini_json_payload(payload_sanitized)
    except GeminiSubtitlesError:
        pass

    # 2) safe_json_loads on sanitized (includes extra cleanup like smart quotes, BOM, etc.)
    try:
        return _safe_json_loads(payload_sanitized)
    except GeminiSubtitlesError:
        pass

    # 3) safe_json_loads on raw extracted block (sometimes sanitize can be neutral)
    try:
        return _safe_json_loads(payload_text)
    except GeminiSubtitlesError:
        pass

    # 4) python literal fallback (validate structure before returning)
    try:
        data = ast.literal_eval(payload_sanitized)
        if isinstance(data, dict):
            # reuse existing validation: must have segments list
            return parse_gemini_json_payload(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass

    # 5) heuristic single-quote fix (apply on sanitized)
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
    try:
        fixed = sanitize_string_literals(fixed)
    except Exception:
        pass

    try:
        return _safe_json_loads(fixed)
    except GeminiSubtitlesError:
        pass

    # 6) repair fallback (best-effort; never crash the whole service if repair fails)
    if allow_repair:
        try:
            repaired_raw = _repair_json_with_gemini(payload_text)
            repaired_block = extract_json_block(repaired_raw)

            try:
                repaired_sanitized = sanitize_string_literals(repaired_block)
            except Exception:
                repaired_sanitized = repaired_block

            try:
                return _safe_json_loads(repaired_block)
            except GeminiSubtitlesError:
                return _safe_json_loads(repaired_sanitized)
        except Exception:
            pass

    logger.warning("Gemini subtitles did not return valid JSON. Snippet: %s", snippet)
    raise GeminiSubtitlesError(f"Gemini subtitles did not return valid JSON. Snippet: {snippet}")



def translate_and_segment_with_gemini(
    origin_srt_text: str,
    target_lang: str = "my",
    *,
    allow_repair: bool = True,
    debug_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    # 使用 Gemini 把 SRT 字幕翻译成缅甸语，并做场景分段。

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
    data = parse_gemini_subtitle_payload(
        raw_text,
        allow_repair=allow_repair,
        debug_dir=debug_dir,
    )

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

    return _ensure_scenes(data)


def transcribe_translate_and_segment_with_gemini(
    video_path: Path,
    target_lang: str = "my",
    *,
    allow_repair: bool = True,
    debug_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    # 使用 Gemini 2.0 Flash 对原始视频做转写 + 翻译 + 场景切分。

    返回结构与 translate_and_segment_with_gemini 对齐：
    {
      "language": "<source_language_code>",
      "segments": [...],
      "scenes": [...]
    }
    """
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
                    {
                        "inline_data": {
                            "mime_type": "video/mp4",
                            "data": encoded,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 4096,
            "temperature": 0,
            "candidateCount": 1,
        },
    }

    resp_json = _call_gemini_with_payload(payload)
    raw_text = _extract_text(resp_json)

    try:
        data = parse_gemini_subtitle_payload(
            raw_text,
            allow_repair=allow_repair,
            debug_dir=debug_dir,
        )
    except GeminiSubtitlesError as exc:
        logger.error("%s", exc)
        raise

    if not isinstance(data, dict):
        raise GeminiSubtitlesError("Gemini subtitles JSON root must be an object")

    language = data.get("language")
    if not isinstance(language, str):
        raise GeminiSubtitlesError("Gemini subtitles JSON must include a language code")

    return _ensure_scenes(data)


def _is_truncated_payload(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    if stripped.endswith("...") or stripped.endswith("\u2026"):
        return True
    open_braces = stripped.count("{")
    close_braces = stripped.count("}")
    if open_braces > close_braces:
        return True
    if stripped[-1] not in ("}", "]"):
        return True
    return False


def _parse_translation_payload(raw_text: str) -> dict[int, str]:
    payload_text = raw_text
    try:
        payload_text = extract_json_block(raw_text)
    except Exception:
        payload_text = raw_text

    payload_text = _TRAILING_COMMA_RE.sub(r"\1", payload_text)
    try:
        payload_text = sanitize_string_literals(payload_text)
    except Exception:
        pass

    data = _safe_json_loads(payload_text)

    if isinstance(data, dict):
        items = data.get("translations") or data.get("segments") or []
    elif isinstance(data, list):
        items = data
    else:
        raise GeminiSubtitlesError("Gemini translation payload must be list or object")

    translations: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("index") or item.get("idx")
        text = item.get("mm") or item.get("translation") or item.get("target")
        if idx is None or text is None:
            continue
        try:
            translations[int(idx)] = str(text).strip()
        except Exception:
            continue
    if not translations:
        raise GeminiSubtitlesError("Gemini translation payload empty")
    return translations


def translate_segments_with_gemini(
    *,
    segments: List[Dict[str, Any]],
    target_lang: str = "my",
    debug_dir: Path | None = None,
    chunk_size: int = 30,
    retries: int = 2,
) -> dict[int, str]:
    translations: dict[int, str] = {}
    if not segments:
        return translations

    for offset in range(0, len(segments), chunk_size):
        chunk = segments[offset : offset + chunk_size]
        payload = [
            {"index": seg.get("index"), "origin": seg.get("origin", "")}
            for seg in chunk
        ]
        prompt = f"""
You are a subtitle translator.

Translate the following segments into target language "{target_lang}".
Return ONLY JSON with this exact shape:
{{"translations":[{{"index":1,"mm":"..."}},...]}}

Rules:
- Preserve indices exactly.
- Only output JSON. No markdown or extra text.

Segments:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

        last_error: str | None = None
        for attempt in range(retries + 1):
            resp_json = _call_gemini(prompt)
            raw_text = _extract_text(resp_json)
            if _is_truncated_payload(raw_text) and attempt < retries:
                last_error = "truncated"
                continue
            try:
                chunk_translations = _parse_translation_payload(raw_text)
                translations.update(chunk_translations)
                last_error = None
                break
            except GeminiSubtitlesError as exc:
                last_error = str(exc)
                if attempt >= retries:
                    break

        if last_error:
            raise GeminiSubtitlesError(last_error)

    return translations


if __name__ == "__main__":
    samples = [
        """```json
        {"segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}]}
        ```""",
        """{"segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1,}],}""",
        """Some preface text {"segments":[{"index":1,"start":0.0,"end":1.0,"origin":"a","mm":"b","scene_id":1}]} trailing""",
    ]
    for sample in samples:
        print(_safe_json_loads(sample))
