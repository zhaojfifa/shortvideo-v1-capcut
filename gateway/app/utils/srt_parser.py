
from typing import List, Dict

def segments_to_srt(segments: List[Dict], text_key: str = "text") -> str:
    """Convert a list of segment dicts to SRT text using the given text key."""

    def format_timestamp(seconds: float) -> str:
        milliseconds = max(int(round(seconds * 1000)), 0)
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        text = (seg.get(text_key) or "").strip()
        timestamp = f"{format_timestamp(start)} --> {format_timestamp(end)}"
        lines.extend([str(idx), timestamp, text, ""])

    return "\n".join(lines).strip() + "\n" if lines else ""
