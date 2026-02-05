from functools import lru_cache
import os
from typing import Dict

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    # Workspace root for shortvideo V1 pipeline
    workspace_root: str = Field(
        "/opt/render/project/src/video_workspace/tv1_validation",
        env="WORKSPACE_ROOT",
    )

    # Xiongmao short-video parser backend (supports Douyin/TikTok/XHS)
    xiongmao_api_base: str = Field(
        "https://api.guijiangpan.com",
        env="XIONGMAO_API_BASE",
    )
    xiongmao_api_key: str = Field("", env="XIONGMAO_API_KEY")
    xiongmao_app_id: str = Field("xxmQsyByAk", env="XIONGMAO_APP_ID")

    # Legacy aliases (kept for backward compatibility; prefer XIONGMAO_* envs)
    douyin_api_base: str = Field(
        "https://api.guijiangpan.com",
        env="DOUYIN_API_BASE",
    )
    douyin_api_key: str = Field("", env="DOUYIN_API_KEY")

    # OpenAI (Whisper + GPT) – can be left empty if we only use Gemini
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    openai_api_base: str = Field("https://api.openai.com/v1", env="OPENAI_API_BASE")
    whisper_model: str = Field("whisper-1", env="WHISPER_MODEL")
    gpt_model: str = Field("gpt-4o-mini", env="GPT_MODEL")
    asr_backend: str = Field("whisper", env="ASR_BACKEND")
    subtitles_backend: str = Field("gemini", env="SUBTITLES_BACKEND")
    # 当 SUBTITLES_BACKEND == "gemini" 时：
    # - 如果已有 origin.srt，直接翻译+场景切分；
    # - 如果没有，则使用 raw/<task_id>.mp4 让 Gemini 直接转写+翻译，完全不依赖 OPENAI_API_KEY。

    # Gemini backend for subtitles / translation
    gemini_api_key: str | None = Field(None, env="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.0-flash", env="GEMINI_MODEL")
    gemini_base_url: str = Field(
        "https://generativelanguage.googleapis.com/v1beta", env="GEMINI_BASE_URL"
    )

    # LOVO TTS
    lovo_base_url: str = Field(
        "https://api.genny.lovo.ai/api/v1",
        env="LOVO_BASE_URL",
    )
    lovo_api_key: str = Field("", env="LOVO_API_KEY")
    lovo_voice_id_mm: str = Field("mm_female_1", env="LOVO_VOICE_ID_MM")
    lovo_speaker_mm_female_1: str | None = Field(
        None,
        env="LOVO_SPEAKER_MM_FEMALE_1",
    )
    lovo_speaker_style_mm_female_1: str | None = Field(
        None,
        env="LOVO_SPEAKER_STYLE_MM_FEMALE_1",
    )

    # Edge-TTS
    edge_tts_voice_map: Dict[str, str] = Field(
        default_factory=lambda: {
            "mm_female_1": "my-MM-NilarNeural",
            "mm_male_1": "my-MM-ThihaNeural",
        }
    )
    edge_tts_rate: str = Field("+0%", env="EDGE_TTS_RATE")
    edge_tts_volume: str = Field("+0%", env="EDGE_TTS_VOLUME")

    # Dubbing provider selection
    dub_provider: str = Field("edge-tts", env="DUB_PROVIDER")

    # UI language settings
    ui_primary_lang: str = Field("zh", env="UI_PRIMARY_LANG")
    ui_secondary_lang: str = Field("en", env="UI_SECONDARY_LANG")
    ui_show_secondary: bool = Field(True, env="UI_SHOW_SECONDARY")
    ui_mobile_prefix_enabled: bool = Field(True, env="UI_MOBILE_PREFIX_ENABLED")
    enable_apollo_avatar: bool = Field(False, env="ENABLE_APOLLO_AVATAR")
    apollo_avatar_live_enabled: bool = Field(False, env="APOLLO_AVATAR_LIVE_ENABLED")
    apollo_avatar_provider: str = Field("fal_wan26_flash", env="APOLLO_AVATAR_PROVIDER")
    apollo_avatar_live_model: str = Field(
        "wan/v2.6/image-to-video/flash",
        env="APOLLO_AVATAR_LIVE_MODEL",
    )
    apollo_avatar_live_timeout_sec: int = Field(300, env="APOLLO_AVATAR_LIVE_TIMEOUT_SEC")
    demo_asset_base_url: str = Field("", env="DEMO_ASSET_BASE_URL")
# === Storage Configuration (PR-0B) ===
    STORAGE_BACKEND: str = "local"  # 选项: "local", "s3"
    
    # Cloudflare R2 Credentials
    R2_ACCESS_KEY: str = ""
    R2_SECRET_KEY: str = ""
    R2_ENDPOINT: str = ""
    R2_BUCKET_NAME: str = "shortvideo-assets"
    
    # Local Storage Root
    WORKSPACE_ROOT: str = "./data_debug"
    # =====================================
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Convenient singleton-style accessor
settings = get_settings()
DEMO_ASSET_BASE_URL = os.getenv("DEMO_ASSET_BASE_URL", "").rstrip("/")
APOLLO_AVATAR_PROVIDER = os.getenv("APOLLO_AVATAR_PROVIDER", "fal_wan26_flash")



def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


FAL_KEY = _env_str("FAL_KEY", "")
FAL_WAN26_MODEL_ID = _env_str("FAL_WAN26_MODEL_ID", "wan/v2.6/image-to-video/flash")
FAL_WAN26_FLASH_MODEL = _env_str("FAL_WAN26_FLASH_MODEL", "wan/v2.6/image-to-video/flash")
WAN26_TIMEOUT_SEC = _env_int("WAN26_TIMEOUT_SEC", 900)
WAN26_POLL_INTERVAL_SEC = _env_float("WAN26_POLL_INTERVAL_SEC", 2.0)
WAN26_POLL_MAX_INTERVAL_SEC = _env_float("WAN26_POLL_MAX_INTERVAL_SEC", 8.0)
WAN26_RESOLUTION = _env_str("WAN26_RESOLUTION", "1080p")
APOLLO_AVATAR_LIVE_MODEL = _env_str(
    "APOLLO_AVATAR_LIVE_MODEL",
    FAL_WAN26_FLASH_MODEL or FAL_WAN26_MODEL_ID or "wan/v2.6/image-to-video/flash",
)
APOLLO_AVATAR_LIVE_TIMEOUT_SEC = _env_int("APOLLO_AVATAR_LIVE_TIMEOUT_SEC", 300)
# ============================================================
#  Dependency Injection Factory (PR-0B)
# ============================================================

def create_storage_service():
    """
    Storage service factory.
    Composition root should call this and register the instance.
    """
    settings = get_settings()
    # log for local visibility
    print(f"[System] Initializing Storage Service: {settings.STORAGE_BACKEND}")

    if settings.STORAGE_BACKEND == "s3":
        from gateway.app.adapters.storage_r2 import R2StorageService

        return R2StorageService(
            access_key_id=settings.R2_ACCESS_KEY,
            secret_access_key=settings.R2_SECRET_KEY,
            endpoint_url=settings.R2_ENDPOINT,
            bucket_name=settings.R2_BUCKET_NAME,
        )

    from gateway.app.adapters.storage_local import LocalStorageService

    root_dir = getattr(settings, "WORKSPACE_ROOT", "./data_debug")
    return LocalStorageService(root_dir=root_dir)
