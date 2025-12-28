from __future__ import annotations

import asyncio
import re
from pathlib import Path


class EdgeTTSError(RuntimeError):
    pass


try:
    import edge_tts  # pip install edge-tts

    EDGE_TTS_AVAILABLE = True
except Exception as e:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False
    _IMPORT_ERR = e


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _srt_to_text(srt_text: str) -> str:
    blocks = [b for b in srt_text.split("\n\n") if b.strip()]
    lines_out: list[str] = []
    for block in blocks:
        text_lines: list[str] = []
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                continue
            if "-->" in s or _SRT_TIME_RE.search(s):
                continue
            text_lines.append(s)
        if text_lines:
            lines_out.append(" ".join(text_lines))
    return "\n".join(lines_out).strip()


def _run_async(coro) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(coro)


def generate_edge_tts_wav_from_srt(
    srt_path: Path,
    output_path: Path,
    *,
    voice: str,
    rate: str,
    pitch: str,
) -> None:
    if not EDGE_TTS_AVAILABLE:
        raise EdgeTTSError(f"edge-tts not available: {_IMPORT_ERR}")

    text = _srt_to_text(srt_path.read_text(encoding="utf-8"))
    if not text:
        raise EdgeTTSError("SRT contains no transcribable text")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    _run_async(communicate.save(str(output_path)))

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise EdgeTTSError("Edge-TTS did not produce audio output")
