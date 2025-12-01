from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    xiongmao_api_base: str = Field(
        "https://api.guijianpan.com", env="XIONGMAO_API_BASE"
    )
    xiongmao_app_id: str = Field("xxmQsyByAk", env="XIONGMAO_APP_ID")
    xiongmao_api_key: str = Field(..., env="XIONGMAO_API_KEY")

    class Config:
        case_sensitive = False


def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]


settings = get_settings()
