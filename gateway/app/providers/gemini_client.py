"""Thin wrapper for Gemini client access."""

import logging
from functools import lru_cache

from google import genai

from gateway.app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key)


def call_gemini(prompt: str) -> str:
    """Call Gemini with a single text prompt and return the response text."""

    client = get_gemini_client()
    settings = get_settings()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
    except Exception as exc:  # pragma: no cover - external request guard
        logger.exception("Gemini generate_content failed")
        raise

    text = getattr(response, "text", "") or ""
    if not text.strip():
        raise ValueError("Gemini response was empty")
    return text
