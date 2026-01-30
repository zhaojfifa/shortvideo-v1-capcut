from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException

from gateway.app.core.workspace import raw_input_path, workspace_root
from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.utils.timing import log_step_timing

logger = logging.getLogger(__name__)

DEFAULT_MIN_SCENE_SEC = 6.0
DEFAULT_MAX_SCENE_SEC = 15.0
DEFAULT_MIN_LINES = 3
DEFAULT_MAX_LINES = 5

SRT_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,\.]\d{3})"
)
SRT_LINE_TIME_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


@dataclass
class SrtEntry:
    start: float
    end: float
    text: str


@dataclass
class SceneRange:
    start: float
    end: float


def _ffmpeg_path() -> str:
    ffmpeg = shutil.which("ffmpeg")  # type: ignore[name-defined]
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    return ffmpeg


def _run_ffmpeg(args: list[str]) -> None:
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")


def _slice_video(src: Path, dst: Path, start: float, end: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-c:v",
        "copy",
        str(dst),
    ]
    _run_ffmpeg(cmd)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"video slice missing: {dst}")


def _slice_audio(src: Path, dst: Path, start: float, end: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dst),
    ]
    try:
        _run_ffmpeg(cmd)
    except RuntimeError:
        duration = max(end - start, 0.1)
        _generate_silence_audio(dst, duration)
    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError(f"audio slice missing: {dst}")


def _generate_silence_audio(dst: Path, seconds: float) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-t",
        f"{seconds:.3f}",
        "-acodec",
        "pcm_s16le",
        str(dst),
    ]
    _run_ffmpeg(cmd)


def _derive_scenes_from_srt(
    entries: list[SrtEntry],
    *,
    min_scene_sec: float,
    max_scene_sec: float,
    min_lines: int,
    max_lines: int,
) -> list[SceneRange]:
    if not entries:
        raise RuntimeError("no srt entries to derive scenes")

    scenes: list[SceneRange] = []
    scene_start = entries[0].start
    count = 0

    for idx, entry in enumerate(entries):
        count += 1
        scene_end = entry.end
        duration = scene_end - scene_start
        next_end = entries[idx + 1].end if idx + 1 < len(entries) else None

        cut = False
        if duration >= max_scene_sec:
            cut = True
        elif count >= max_lines:
            cut = True
        elif count >= min_lines and duration >= min_scene_sec:
            if next_end is None or (next_end - scene_start) > max_scene_sec:
                cut = True

        if cut:
            scenes.append(SceneRange(start=scene_start, end=scene_end))
            if idx + 1 < len(entries):
                scene_start = entries[idx + 1].start
            count = 0

    if count > 0 and scenes:
        last_end = entries[-1].end
        scenes.append(SceneRange(start=scene_start, end=last_end))
    if not scenes:
        scenes.append(SceneRange(start=entries[0].start, end=entries[-1].end))
    return scenes


def _parse_srt(text: str) -> list[SrtEntry]:
    blocks = [b for b in text.strip().split("\n\n") if b.strip()]
    entries: list[SrtEntry] = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if lines[0].strip().isdigit() else lines[0]
        match = SRT_TIME_RE.search(time_line)
        if not match:
            continue
        start = _parse_srt_time(match.group("start"))
        end = _parse_srt_time(match.group("end"))
        text_lines = lines[2:] if lines[0].strip().isdigit() else lines[1:]
        entries.append(SrtEntry(start=start, end=end, text="\n".join(text_lines)))
    return entries


def _srt_to_plain_text(srt_text: str) -> str:
    lines: list[str] = []
    for raw in srt_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if SRT_LINE_TIME_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + ("\n" if lines else "")


def _write_scene_subtitles(scene_dir: Path, srt_content: str) -> None:
    scene_dir.mkdir(parents=True, exist_ok=True)
    (scene_dir / "subs.srt").write_text(srt_content, encoding="utf-8")
    (scene_dir / "subs.txt").write_text(
        _srt_to_plain_text(srt_content),
        encoding="utf-8",
    )


def _parse_srt_time(value: str) -> float:
    h, m, rest = value.replace(",", ".").split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _format_srt_time(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    ms_total = int(round(seconds * 1000))
    ms = ms_total % 1000
    s_total = ms_total // 1000
    s = s_total % 60
    m_total = s_total // 60
    m = m_total % 60
    h = m_total // 60
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _clip_srt(entries: Iterable[SrtEntry], start: float, end: float) -> str:
    out_lines: list[str] = []
    idx = 1
    for entry in entries:
        e_start = float(entry.start)
        e_end = float(entry.end)
        if e_end <= start or e_start >= end:
            continue
        new_start = max(e_start, start) - start
        new_end = min(e_end, end) - start
        if new_end <= 0:
            continue
        out_lines.append(str(idx))
        out_lines.append(f"{_format_srt_time(new_start)} --> {_format_srt_time(new_end)}")
        out_lines.append(entry.text.strip())
        out_lines.append("")
        idx += 1
    return "\n".join(out_lines).strip() + ("\n" if idx > 1 else "")


def _find_source_srt(task_id: str) -> tuple[Path, str]:
    deliver_subs = workspace_root() / "deliver" / "subtitles" / task_id
    if deliver_subs.exists():
        subtitles_json = deliver_subs / "subtitles.json"
        if not subtitles_json.exists():
            raise HTTPException(
                status_code=400,
                detail="subtitles not ready; run subtitles first",
            )
        for lang in ("mm", "my"):
            srt_path = deliver_subs / f"{lang}.srt"
            if srt_path.exists():
                return srt_path, lang
        origin = deliver_subs / "origin.srt"
        if origin.exists():
            return origin, "origin"

    base = workspace_root() / "deliver" / "packs" / task_id / "subs"
    for lang in ("mm", "my"):
        srt_path = base / f"{lang}.srt"
        if srt_path.exists():
            return srt_path, lang
    origin = base / "origin.srt"
    if origin.exists():
        return origin, "origin"
    raise HTTPException(status_code=400, detail="subtitles not ready; run subtitles first")


README_TEMPLATE = """# Scenes.zip 使用说明 / Scenes.zip အသုံးပြုနည်း

## 1. 这是什么？ / ဒီကဘာလဲ？
中文：
Scenes.zip 是将本次 Task 的原视频按字幕时间切分成多个可复用“场景片段（MSC）”的素材包。
每个场景都包含：视频片段 video.mp4、音频 audio.wav、字幕 subs.srt、以及说明文件 scene.json。

缅文：
Scenes.zip သည် ဒီ Task ရဲ့ ဗီဒီယိုကို စာတန်းထိုးအချိန်အလိုက် အပိုင်းများ (MSC) အဖြစ် ခွဲထားတဲ့ အစိတ်အပိုင်းပစ္စည်းအစုပါ။
Scene တစ်ခုချင်းစီမှာ video.mp4, audio.wav, subs.srt, scene.json ပါဝင်ပါတယ်။

---

## 2. 文件结构 / ဖိုင်ဖွဲ့စည်းပုံ

deliver/scenes/{task_id}/
README.md
scenes_manifest.json
scenes/
scene_001/
video.mp4
audio.wav
subs.srt
scene.json

说明 / ရှင်းလင်းချက်：
- scenes_manifest.json：场景清单（可忽略，不需要编辑）
- scene.json：每个场景的开始/结束时间与来源说明（可忽略，不需要编辑）

---

## 3. 如何使用（运营/剪辑） / အသုံးပြုနည်း (Operation/Editing)

### A) 快速查看每个场景 / Scene တစ်ခုချင်းစီကို မြန်မြန်ကြည့်ရန်
中文：
打开 scenes/scene_001/video.mp4 即可预览该片段内容；subs.srt 是对应字幕。

缅文：
scenes/scene_001/video.mp4 ကိုဖွင့်ပြီး အပိုင်းကိုကြည့်နိုင်ပါတယ်။ subs.srt က သက်ဆိုင်ရာ စာတန်းထိုးပါ။

### B) 在手机 YouCut 中使用（手工导入） / ဖုန်း YouCut တွင် အသုံးပြုရန် (လက်ဖြင့်ထည့်သွင်း)
中文（建议流程）：
1) 解压 Scenes.zip 到手机本地（文件管理器）。
2) 打开 YouCut → 新建项目。
3) 逐个导入你需要的 scenes/scene_xxx/video.mp4（按你想要的顺序）。
4) 如需配音：可将 audio.wav 作为音频素材导入（可选）。
5) 如需字幕：YouCut 通常不支持直接导入 SRT，请按 subs.srt 手工粘贴字幕，或交给剪辑师在 CapCut/PC 工具中处理。

缅文：
1) Scenes.zip ကို ဖုန်းထဲမှာ unzip လုပ်ပါ။
2) YouCut ကိုဖွင့် → Project အသစ်ဖန်တီးပါ။
3) scenes/scene_xxx/video.mp4 တွေကို လိုအပ်သလို အစဉ်လိုက် ထည့်ပါ။
4) အသံလိုပါက audio.wav ကို Audio အဖြစ် ထည့်နိုင်ပါတယ် (ရွေးချယ်နိုင်)။
5) Subtitle အတွက် YouCut မှ SRT တိုက်ရိုက်မသွင်းနိုင်ပါက subs.srt ကိုကြည့်ပြီး လက်ဖြင့်ထည့်ပါ (သို့) CapCut/PC tool သို့ ပို့ပါ။

---

## 4. 常见问题 / မကြာခဏမေးသောမေးခွန်းများ

Q1：我需要打开 JSON 吗？/ JSON ဖွင့်ဖို့လိုလား？
- 中文：不需要。只用 video.mp4 即可。
- 缅文：မလိုပါ။ video.mp4 ကိုပဲ အသုံးပြု即可။

Q2：为什么还有 audio.wav？/ audio.wav ဘာကြောင့်ပါလဲ？
- 中文：方便剪辑时替换/对齐音频。默认包含。
- 缅文：Edit လုပ်ရာမှာ အသံကို ပြောင်း/ညှိဖို့အတွက်ပါ။ Default အနေဖြင့် ပါဝင်ပါတယ်။

Q3：Scenes.zip 会影响 Pack.zip 吗？/ Scenes.zip က Pack.zip ကိုသက်ရောက်မလား？
- 中文：不会。两个包相互独立。
- 缅文：မသက်ရောက်ပါ။ နှစ်ခု သီးခြားပါ။
"""


def _write_readme(dst: Path, task_id: str) -> None:
    dst.write_text(README_TEMPLATE.format(task_id=task_id), encoding="utf-8")


def generate_scenes_package(
    task_id: str,
    *,
    min_scene_sec: float = DEFAULT_MIN_SCENE_SEC,
    max_scene_sec: float = DEFAULT_MAX_SCENE_SEC,
    min_lines: int = DEFAULT_MIN_LINES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> dict:
    raw = raw_input_path(task_id)
    if not raw.exists():
        raise RuntimeError("raw video not found")

    source_srt, source_lang = _find_source_srt(task_id)
    srt_entries = _parse_srt(source_srt.read_text(encoding="utf-8"))
    scenes = _derive_scenes_from_srt(
        srt_entries,
        min_scene_sec=min_scene_sec,
        max_scene_sec=max_scene_sec,
        min_lines=min_lines,
        max_lines=max_lines,
    )

    out_root = workspace_root() / "deliver" / "scenes" / task_id
    package_root = out_root / "scenes_package"
    scenes_root = package_root / "scenes"
    package_root.mkdir(parents=True, exist_ok=True)
    scenes_root.mkdir(parents=True, exist_ok=True)

    manifest_scenes: list[dict] = []

    for idx, scene in enumerate(scenes, start=1):
        scene_id = f"scene_{idx:03d}"
        scene_dir = scenes_root / scene_id
        scene_dir.mkdir(parents=True, exist_ok=True)

        video_path = scene_dir / "video.mp4"
        audio_path = scene_dir / "audio.wav"
        scene_json_path = scene_dir / "scene.json"

        _slice_video(raw, video_path, scene.start, scene.end)
        _slice_audio(raw, audio_path, scene.start, scene.end)

        clipped_srt = _clip_srt(srt_entries, scene.start, scene.end)
        _write_scene_subtitles(scene_dir, clipped_srt)

        preview = ""
        for entry in srt_entries:
            if entry.end > scene.start and entry.start < scene.end:
                preview = entry.text.splitlines()[0].strip()
                break

        scene_payload = {
            "scene_id": scene_id,
            "source": {
                "task_id": task_id,
                "origin_video": str(raw),
                "time_range": [round(scene.start, 3), round(scene.end, 3)],
            },
            "semantics": {
                "role": "unknown",
                "language": source_lang,
                "summary": preview or "",
            },
            "assets": {
                "video": "video.mp4",
                "audio": "audio.wav",
                "subs": "subs.srt",
            },
        }
        scene_json_path.write_text(
            json.dumps(scene_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        duration = scene.end - scene.start
        manifest_scenes.append(
            {
                "scene_id": scene_id,
                "start": round(scene.start, 3),
                "end": round(scene.end, 3),
                "duration": round(duration, 3),
                "role": "unknown",
                "dir": f"scenes/{scene_id}",
            }
        )

    try:
        subs_rel = str(source_srt.resolve().relative_to(workspace_root()))
    except Exception:
        subs_rel = str(source_srt)
    try:
        raw_rel = str(raw.resolve().relative_to(workspace_root()))
    except Exception:
        raw_rel = str(raw)

    manifest = {
        "version": "1.8",
        "task_id": task_id,
        "language": source_lang,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "raw_video": raw_rel,
            "subs": subs_rel,
        },
        "scenes": manifest_scenes,
    }
    manifest_path = package_root / "scenes_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    readme_path = package_root / "README.md"
    _write_readme(readme_path, task_id)

    zip_path = out_root / "scenes.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for item in package_root.rglob("*"):
            if item.is_file():
                arcname = Path("deliver") / "scenes" / task_id / item.relative_to(package_root)
                zf.write(item, arcname=arcname.as_posix())

    storage = get_storage_service()
    scenes_key = f"deliver/scenes/{task_id}/scenes.zip"
    storage.upload_file(str(zip_path), scenes_key, content_type="application/zip")

    return {
        "task_id": task_id,
        "scenes_key": scenes_key,
        "scenes_count": len(manifest_scenes),
        "zip_path": str(zip_path),
        "manifest_path": str(manifest_path),
    }


def _task_value(task: object, field: str) -> str | None:
    if isinstance(task, dict):
        value = task.get(field)
    else:
        value = getattr(task, field, None)
    return str(value) if value else None


def run_scenes_build(task_id: str, update_task) -> dict:
    start_time = time.perf_counter()
    update_task(task_id, {"scenes_status": "running", "scenes_error": None})
    try:
        result = generate_scenes_package(task_id)
        update_task(
            task_id,
            {
                "scenes_status": "ready",
                "scenes_key": result.get("scenes_key"),
                "scenes_count": result.get("scenes_count"),
                "scenes_error": None,
            },
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive logging
        update_task(task_id, {"scenes_status": "error", "scenes_error": str(exc)})
        raise
    finally:
        log_step_timing(
            logger,
            task_id=task_id,
            step="scenes",
            start_time=start_time,
        )


def enqueue_scenes_build(
    task_id: str,
    *,
    task: object,
    object_exists,
    update_task,
    background_tasks,
) -> dict:
    scenes_key = _task_value(task, "scenes_key")
    if scenes_key and object_exists(str(scenes_key)):
        return {
            "task_id": task_id,
            "status": "already_ready",
            "scenes_key": scenes_key,
            "message": "Scenes already ready",
            "error": None,
        }

    update_task(task_id, {"scenes_status": "queued", "scenes_error": None})
    background_tasks.add_task(run_scenes_build, task_id, update_task)
    return {
        "task_id": task_id,
        "status": "queued",
        "scenes_key": None,
        "message": "Scenes build queued",
        "error": None,
    }
