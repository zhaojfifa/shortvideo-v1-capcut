import argparse
from pathlib import Path

from pipeline.dubbing_lovo import synthesize_burmese_voice
from pipeline.fetch_raw_gateway import fetch_raw_via_gateway
from pipeline.pack_for_capcut import pack_for_capcut
from pipeline.transcribe_translate import (
    extract_audio,
    transcribe_with_whisper,
    translate_subtitles_to_burmese,
)


def run_pipeline(task_id: str, platform: str, link: str | None, input_file: str | None) -> None:
    if input_file:
        raw_path = Path(input_file)
    else:
        if not link:
            raise ValueError("--link is required when --input-file is not provided")
        raw_path = fetch_raw_via_gateway(task_id, platform, link)
    print(f"[OK] raw video: {raw_path}")

    audio_path = extract_audio(task_id, raw_path)
    print(f"[OK] extracted audio: {audio_path}")

    origin_srt = transcribe_with_whisper(task_id, audio_path)
    print(f"[OK] original subtitles: {origin_srt}")

    burmese_srt = translate_subtitles_to_burmese(task_id, origin_srt)
    print(f"[OK] burmese subtitles: {burmese_srt}")

    burmese_audio = synthesize_burmese_voice(task_id, burmese_srt)
    print(f"[OK] burmese voiceover: {burmese_audio}")

    pack_path = pack_for_capcut(task_id, raw_path, burmese_audio, burmese_srt)
    print(f"[OK] capcut pack: {pack_path}")


def main():
    parser = argparse.ArgumentParser(description="Run ShortVideo V1 pipeline")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--platform", default="douyin")
    parser.add_argument("--link")
    parser.add_argument("--input-file")
    args = parser.parse_args()

    run_pipeline(args.task_id, args.platform, args.link, args.input_file)


if __name__ == "__main__":
    main()
