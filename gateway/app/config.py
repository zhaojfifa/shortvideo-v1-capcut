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
    ui_secondary_lang: str = Field("my", env="UI_SECONDARY_LANG")
    ui_show_secondary: bool = Field(True, env="UI_SHOW_SECONDARY")
    ui_mobile_prefix_enabled: bool = Field(True, env="UI_MOBILE_PREFIX_ENABLED")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Convenient singleton-style accessor
settings = get_settings()
