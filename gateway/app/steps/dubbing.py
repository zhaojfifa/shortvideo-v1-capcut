import os
import json
import logging
import asyncio
from gateway.app.config import get_storage_service, get_settings
from gateway.app.utils.keys import KeyBuilder
from gateway.app.utils.languages import get_default_voice

# Adapter for existing edge_tts provider
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

    # 1. Download SSOT (subtitles.json)
    sub_key = KeyBuilder.build(tenant, project, task_id, "artifacts/subtitles.json")
    
    # Construct local temp path
    local_dir = os.path.join(settings.WORKSPACE_ROOT, tenant, project, task_id)
    os.makedirs(local_dir, exist_ok=True)
    local_sub_path = os.path.join(local_dir, "subtitles.json")
    
    # Check cloud storage
    if not storage.exists(sub_key):
        error_msg = f"Subtitles JSON not found at {sub_key}. SSOT Broken."
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
        
    storage.download_file(sub_key, local_sub_path)
    
    with open(local_sub_path, "r", encoding="utf-8") as f:
        sub_data = json.load(f)
        
    segments = sub_data.get("segments", [])
    if not segments:
        logger.warning("No segments found in subtitles.json")
        return

    # 2. Prepare Voice Manifest
    voice_manifest = {
        "schema_version": "0.1",
        "task_id": task_id,
        "provider": "edge-tts",
        "voice_id": get_default_voice(target_lang),
        "segments_map": {} 
    }

    # 3. Generate Audio
    full_text = " ".join([seg.get("target", "") for seg in segments])
    
    if not full_text.strip():
        logger.warning("Empty text for dubbing.")
        return

    local_audio_path = os.path.join(local_dir, "full_audio.mp3")
    
    # Call underlying TTS
    await generate_audio_edge_tts(full_text, voice_manifest["voice_id"], local_audio_path)
    
    # 4. Upload Audio
    audio_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/full.mp3")
    storage.upload_file(local_audio_path, audio_key)
    
    # 5. Upload Manifest
    voice_manifest["outputs"] = {"full_audio": audio_key}
    manifest_local_path = os.path.join(local_dir, "voice_manifest.json")
    with open(manifest_local_path, "w", encoding="utf-8") as f:
        json.dump(voice_manifest, f, indent=2)
        
    manifest_key = KeyBuilder.build(tenant, project, task_id, "artifacts/voice/manifest.json")
    storage.upload_file(manifest_local_path, manifest_key)
    
    logger.info(f"Dubbing complete. Manifest saved to {manifest_key}")
