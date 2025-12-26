from functools import lru_cache
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
# ============================================================
#  Dependency Injection Factory (PR-0B)
# ============================================================
from functools import lru_cache

# 全局单例变量
_storage_service_instance = None

def get_storage_service():
    """
    存储服务工厂函数。
    根据环境变量 STORAGE_BACKEND 返回对应的适配器实例 (R2 或 Local)。
    注意：使用函数内 import 以防止循环依赖。
    """
    global _storage_service_instance
    if _storage_service_instance:
        return _storage_service_instance

    settings = get_settings()
    
    # 打印日志方便调试
    print(f"[System] Initializing Storage Service: {settings.STORAGE_BACKEND}")

    if settings.STORAGE_BACKEND == "s3":
        # 动态导入 R2 适配器
        from gateway.app.adapters.storage_r2 import R2StorageService
        _storage_service_instance = R2StorageService(
            access_key=settings.R2_ACCESS_KEY,
            secret_key=settings.R2_SECRET_KEY,
            endpoint_url=settings.R2_ENDPOINT,
            bucket_name=settings.R2_BUCKET_NAME
        )
    else:
        # 动态导入本地适配器
        from gateway.app.adapters.storage_local import LocalStorageService
        # 默认存在 ./data_debug 目录下方便查看
        root_dir = getattr(settings, "WORKSPACE_ROOT", "./data_debug")
        _storage_service_instance = LocalStorageService(root_dir=root_dir)

    return _storage_service_instance