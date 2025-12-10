import subprocess
from pathlib import Path

from openai import OpenAI

from pipeline import config
from pipeline.workspace import subs_dir

client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_API_BASE)


def extract_audio(task_id: str, raw_path: Path) -> Path:
    output_dir = subs_dir()
    out_path = output_dir / f"{task_id}.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def transcribe_with_whisper(task_id: str, audio_path: Path) -> Path:
    """Call OpenAI Whisper API -> edits/subs/<task_id>_origin.srt"""

    out_path = subs_dir() / f"{task_id}_origin.srt"
    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=audio_file,
            response_format="srt",
        )
    out_path.write_text(result, encoding="utf-8")
    return out_path


def translate_subtitles_to_burmese(task_id: str, origin_srt: Path) -> Path:
    """Call OpenAI GPT model to translate SRT content into Burmese -> *_mm.srt"""

    burmese_path = subs_dir() / f"{task_id}_mm.srt"
    origin_content = origin_srt.read_text(encoding="utf-8")
    prompt = (
        "你是一名专业的字幕翻译。请将以下 SRT 内容翻译成缅甸语，"
        "保持 SRT 时间戳和序号格式不变，只翻译文本内容。"
    )
    completion = client.chat.completions.create(
        model=config.GPT_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": origin_content},
        ],
    )
    burmese_text = completion.choices[0].message.content or ""
    burmese_path.write_text(burmese_text, encoding="utf-8")
    return burmese_path
