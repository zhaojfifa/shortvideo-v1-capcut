from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    # Workspace root for shortvideo V1 pipeline
    workspace_root: str = Field(
        "/opt/render/project/src/video_workspace/tv1_validation",
        env="WORKSPACE_ROOT",
    )

    # Douyin / TikTok parser backend
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
    gemini_api_key: str = Field("", env="GEMINI_API_KEY")
    gemini_model: str = Field("models/gemini-2.0-flash", env="GEMINI_MODEL")

    # Subtitles backend selector: 'openai' or 'gemini'
    # NOTE(中文注释): 这个配置决定 Step2 使用哪个字幕后端。默认使用 OpenAI Whisper。
    subtitles_backend: str = Field("openai", env="SUBTITLES_BACKEND")

    # LOVO TTS
    lovo_api_key: str = Field("", env="LOVO_API_KEY")
    lovo_voice_id_mm: str = Field("mm_female_1", env="LOVO_VOICE_ID_MM")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
