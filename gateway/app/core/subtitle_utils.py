"""Subtitle utility helpers used across services.

注意（中文）：将通用的 `preview_lines` 提取到 core 包，避免
services/subtitles.py <-> services/subtitles_openai.py 的循环导入。
这个模块只包含轻量工具，不依赖服务或路由。
"""

from typing import List


def preview_lines(text: str, limit: int = 5) -> List[str]:
    """Return first non-empty text lines excluding SRT indices/timestamps.

    中文说明：用于在不完全解析 SRT 的情况下快速预览字幕文本。
    """
    lines = [line.strip("\ufeff").rstrip("\n") for line in text.splitlines()]
    preview: List[str] = []
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
