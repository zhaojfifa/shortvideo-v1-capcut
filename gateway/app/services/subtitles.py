import logging
from typing import Any

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.workspace import raw_path, relative_to_workspace


class SubtitleError(Exception):
    """Raised when subtitle processing fails."""


async def generate_subtitles(
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = False,
    with_scenes: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    backend = (settings.subtitles_backend or "openai").lower()

    if backend == "gemini":
        from gateway.app.services.subtitles_gemini import generate_with_gemini

        return await generate_with_gemini(
            task_id=task_id,
            target_lang=target_lang,
            with_scenes=with_scenes,
        )
    if backend == "openai":
        from gateway.app.services.subtitles_openai import generate_with_openai

        return await generate_with_openai(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate_enabled=translate_enabled,
            use_ffmpeg_extract=use_ffmpeg_extract,
        )
    if backend == "local":
        origin = raw_path(task_id)
        if not origin.exists():
            raise SubtitleError("raw video not found")
        raise HTTPException(status_code=400, detail="local backend is not implemented")

    logging.error("Unsupported subtitles backend: %s", backend)
    raise HTTPException(status_code=400, detail=f"Unsupported subtitles backend: {backend}")


def preview_lines(text: str, limit: int = 5) -> list[str]:
    lines = [line.strip("\ufeff").rstrip("\n") for line in text.splitlines()]
    preview: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.isdigit() or "-->" in stripped:
            continue
        preview.append(stripped)
        if len(preview) >= limit:
            break
    return preview


def workspace_relative(path) -> str | None:
    if path is None:
        return None
    return relative_to_workspace(path)
