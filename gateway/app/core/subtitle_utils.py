"""Subtitle utility helpers used across services.

注意（中文）：将通用的 `preview_lines` 提取到 core 包，避免
services/subtitles.py <-> services/subtitles_openai.py 的循环导入。
这个模块只包含轻量工具，不依赖服务或路由。
"""

from typing import Iterable, List


def format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp (HH:MM:SS,mmm)."""

    milliseconds = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def segments_to_srt(segments: Iterable[dict], text_key: str = "origin") -> str:
    """Convert a list of segment dicts to SRT text using the given text key."""

    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        text = (seg.get(text_key) or "").strip()
        timestamp = f"{format_timestamp(start)} --> {format_timestamp(end)}"
        lines.extend([str(int(seg.get("index", idx))), timestamp, text, ""])

    return "\n".join(lines).strip() + "\n" if lines else ""


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
