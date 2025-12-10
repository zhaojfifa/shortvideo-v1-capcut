from functools import lru_cache
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

    # Gemini backend for subtitles / translation
    gemini_api_key: str | None = Field(None, env="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-2.0-flash", env="GEMINI_MODEL")
    gemini_base_url: str = Field(
        "https://generativelanguage.googleapis.com/v1beta", env="GEMINI_BASE_URL"
    )

    # LOVO TTS
    lovo_api_key: str = Field("", env="LOVO_API_KEY")
    lovo_voice_id_mm: str = Field("mm_female_1", env="LOVO_VOICE_ID_MM")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Convenient singleton-style accessor
settings = get_settings()
