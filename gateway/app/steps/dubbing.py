import os
import json
import logging
import asyncio
from gateway.app.config import get_storage_service, get_settings
from gateway.app.utils.keys import KeyBuilder
from gateway.app.utils.languages import get_default_voice

# 适配你现有的 edge_tts 位置
from gateway.app.providers.edge_tts import generate_audio_edge_tts 

logger = logging.getLogger(__name__)

async def run_dub_step(task):
    """
    Step 4: Dubbing (SSOT Compliant)
    Reads: artifacts/subtitles.json
    Writes: artifacts/voice/manifest.json, artifacts/voice/*.wav
    """
    settings = get_settings()
    storage = get_storage_service()
    
    task_id = task.id
    tenant = getattr(task, "tenant_id", "default")
    project = getattr(task, "project_id", "default")
    target_lang = getattr(task, "target_lang", "my")

    logger.info(f"Starting Dub Step for task {task_id} (Lang: {target_lang})")

    # 1. 下载 SSOT (subtitles.json)
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    
    # 构造本地临时路径
    local_dir = os.path.join(settings.WORKSPACE_ROOT, tenant, project, task_id)
    os.makedirs(local_dir, exist_ok=True)
    local_sub_path = os.path.join(local_dir, "subtitles.json")
    
    # 如果云端没有 subtitles.json，尝试从旧逻辑恢复或报错
    if not storage.exists(sub_key):
        error_msg = f"Subtitles JSON not found at {sub_key}. SSOT Broken."
        logger.error(error_msg)
        # 这里你可以选择抛出异常，或者为了兼容性暂时尝试读 SRT (但我们现在要推行 PR-0D，所以建议报错)
        raise FileNotFoundError(error_msg)
        
    storage.download_file(sub_key, local_sub_path)
    
    with open(local_sub_path, "r", encoding="utf-8") as f:
        sub_data = json.load(f)
        
    segments = sub_data.get("segments", [])
    if not segments:
        logger.warning("No segments found in subtitles.json")
        return

    # 2. 准备 Voice Manifest
    voice_manifest = {
        "schema_version": "0.1",
        "task_id": task_id,
        "provider": "edge-tts",
        "voice_id": get_default_voice(target_lang),
        "segments_map": {} 
    }

    # 3. 逐段生成音频 (v1.65 先做整段合并的逻辑)
    # 取出所有 target (翻译后的文本)
    full_text = " ".join([seg.get("target", "") for seg in segments])
    
    if not full_text.strip():
        logger.warning("Empty text for dubbing.")
        return

    local_audio_path = os.path.join(local_dir, "full_audio.mp3")
    
    # 调用底层 TTS
    await generate_audio_edge_tts(full_text, voice_manifest["voice_id"], local_audio_path)
    
    # 4. 上传音频
    audio_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/full.mp3")
    storage.upload_file(local_audio_path, audio_key)
    
    # 5. 上传 Manifest
    voice_manifest["outputs"] = {"full_audio": audio_key}
    manifest_local_path = os.path.join(local_dir, "voice_manifest.json")
    with open(manifest_local_path, "w", encoding="utf-8") as f:
        json.dump(voice_manifest, f, indent=2)
        
    manifest_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/manifest.json")
    storage.upload_file(manifest_local_path, manifest_key)
    
    logger.info(f"Dubbing complete. Manifest saved to {manifest_key}")