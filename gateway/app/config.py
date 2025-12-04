from functools import lru_cache
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    workspace_root: str = Field("./workspace", env="WORKSPACE_ROOT")

    xiongmao_api_base: str = Field(
        "https://api.guijianpan.com", env="XIONGMAO_API_BASE"
    )
    xiongmao_app_id: str = Field("xxmQsyByAk", env="XIONGMAO_APP_ID")
    xiongmao_api_key: str = Field(..., env="XIONGMAO_API_KEY")

    openai_api_key: str | None = Field(None, env="OPENAI_API_KEY")
    openai_api_base: str = Field("https://api.openai.com/v1", env="OPENAI_API_BASE")
    whisper_model: str = Field("whisper-1", env="WHISPER_MODEL")
    gpt_model: str = Field("gpt-4o-mini", env="GPT_MODEL")

    lovo_api_key: str | None = Field(None, env="LOVO_API_KEY")
    lovo_voice_id_mm: str = Field("mm_female_1", env="LOVO_VOICE_ID_MM")

    class Config:
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]


settings = get_settings()
