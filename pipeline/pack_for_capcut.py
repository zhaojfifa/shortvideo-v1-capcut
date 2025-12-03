from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from pipeline.workspace import packs_dir

README_TEMPLATE = """CapCut 剪辑包使用说明

1. 在 CapCut 新建项目，导入 zip 解压后的文件。
2. 将 raw.mp4 放入视频轨道。
3. 导入 subs_mm.srt，调整字体样式。
4. 将 audio_mm.wav 放入音频轨道，与字幕对齐。
5. 根据需要添加转场、贴纸等二次创作。
"""


def pack_for_capcut(task_id: str, raw_path: Path, audio_path: Path, subs_path: Path) -> Path:
    """
    Create packs/<task_id>_capcut_pack.zip with:
      - raw.mp4
      - audio_mm.wav
      - subs_mm.srt
      - README.txt (editor instructions)
    """

    pack_root = packs_dir()
    pack_path = pack_root / f"{task_id}_capcut_pack.zip"

    with ZipFile(pack_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.write(raw_path, arcname="raw.mp4")
        zf.write(audio_path, arcname="audio_mm.wav")
        zf.write(subs_path, arcname="subs_mm.srt")
        zf.writestr("README.txt", README_TEMPLATE)

    return pack_path
