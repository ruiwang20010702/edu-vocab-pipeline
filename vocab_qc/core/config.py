"""应用配置."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url_sync: str = "postgresql://localhost:5432/vocab_qc"
    database_url_async: str = "postgresql+asyncpg://localhost:5432/vocab_qc"
    db_echo: bool = False

    ai_api_key: str = ""
    ai_api_base_url: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_max_concurrency: int = 5
    ai_max_retries: int = 3

    max_regenerate_retries: int = 3

    model_config = {"env_prefix": "VOCAB_QC_", "env_file": ".env"}


settings = Settings()
