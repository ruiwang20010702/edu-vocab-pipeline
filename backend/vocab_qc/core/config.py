"""应用配置."""

import warnings

from pydantic_settings import BaseSettings

_INSECURE_JWT_SECRETS = frozenset({"dev-secret-change-in-production", "changeme", ""})


class Settings(BaseSettings):
    env: str = "development"

    database_url_sync: str = "postgresql://localhost:5432/vocab_qc"
    db_echo: bool = False

    ai_api_key: str = ""
    ai_api_base_url: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_max_concurrency: int = 5
    ai_max_retries: int = 3

    max_regenerate_retries: int = 3
    max_upload_size_mb: int = 10

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # 认证
    allowed_email_domains: list[str] = []
    verification_code_expire_minutes: int = 10

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_prefix": "VOCAB_QC_", "env_file": ".env"}


settings = Settings()
