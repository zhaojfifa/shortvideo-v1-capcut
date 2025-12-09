from pathlib import Path

from pathlib import Path

import requests

from pipeline import config
from pipeline.workspace import audio_dir


def _combine_srt_text(srt_path: Path) -> str:
    lines = srt_path.read_text(encoding="utf-8").splitlines()
    text_parts: list[str] = []
    for line in lines:
        if line.strip().isdigit():
            continue
        if "-->" in line:
            continue
        stripped = line.strip()
        if stripped:
            text_parts.append(stripped)
    return " \n".join(text_parts)


def synthesize_burmese_voice(task_id: str, burmese_srt_path: Path) -> Path:
    """
    Read Burmese subtitles, generate a combined Burmese text,
    call LOVO API to synthesize wav, save to edits/audio/<task_id>_mm_vo.wav.
    """

    output_dir = audio_dir()
    out_path = output_dir / f"{task_id}_mm_vo.wav"

    text = _combine_srt_text(burmese_srt_path)
    payload = {
        "text": text,
        "voice_id": config.LOVO_VOICE_ID_MM,
        "output_format": "wav",
    }
    headers = {"Authorization": f"Bearer {config.LOVO_API_KEY}"}

    response = requests.post(
        "https://api.lovo.ai/v1/synthesize",
        json=payload,
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(response.content)

    return out_path
