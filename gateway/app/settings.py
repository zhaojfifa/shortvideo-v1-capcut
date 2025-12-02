# gateway/app/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings for the shortvideo gateway.

    Values are read from environment variables with the same names, e.g.:
      XIONGMAO_API_BASE
      XIONGMAO_APP_ID
      XIONGMAO_API_KEY
    """

    XIONGMAO_API_BASE: str = "https://api.guijianpan.com"
    XIONGMAO_APP_ID: str = "xxmQsyByAk"
    XIONGMAO_API_KEY: str = ""  # 在 Render 环境变量中覆盖

    # Pydantic v2 / pydantic-settings 配置
    model_config = SettingsConfigDict(extra="ignore")
    # 兼容 providers 中使用的小写属性名
    @property
    def xiongmao_api_base(self) -> str:
        return self.XIONGMAO_API_BASE

    @property
    def xiongmao_app_id(self) -> str:
        return self.XIONGMAO_APP_ID

    @property
    def xiongmao_api_key(self) -> str:
        return self.XIONGMAO_API_KEY


settings = Settings()
