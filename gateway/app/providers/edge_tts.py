import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class EdgeTTSError(RuntimeError):
    pass

try:
    import edge_tts  # pip install edge-tts
    EDGE_TTS_AVAILABLE = True
except Exception as e:
    edge_tts = None
    EDGE_TTS_AVAILABLE = False
    _IMPORT_ERR = e

async def generate_audio_edge_tts(text: str, voice: str, output_path: str) -> None:
    if not EDGE_TTS_AVAILABLE:
        raise EdgeTTSError(f"edge-tts not available: {_IMPORT_ERR}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(str(out))
    except Exception as e:
        raise EdgeTTSError(str(e)) from e
