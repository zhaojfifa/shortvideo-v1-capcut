"""Thin wrapper for Gemini client access."""

import logging

import httpx

from gateway.app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

GEMINI_BASE_URL = settings.gemini_base_url
GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model


class GeminiClientError(RuntimeError):
    pass


async def generate_text(prompt: str, *, temperature: float = 0.3, max_output_tokens: int = 2048) -> str:
    """
    Call Google Gemini `generateContent` and return the model text
    (candidates[0].content.parts[0].text).

    This helper is used by the subtitles service to translate SRT.
    """
    if not GEMINI_API_KEY:
        raise GeminiClientError("GEMINI_API_KEY is not configured")

    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.8,
            "maxOutputTokens": max_output_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Gemini HTTP error: %s", exc.response.text)
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

    data = resp.json()
    try:
        candidates = data["candidates"]
        first = candidates[0]
        parts = first["content"]["parts"]
        text = parts[0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Unexpected Gemini response structure: %r", data)
        raise GeminiClientError("Gemini response has unexpected structure") from exc

    return text.strip()
