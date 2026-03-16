"""应用配置."""

import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_INSECURE_JWT_SECRETS = frozenset({"dev-secret-change-in-production", "changeme", ""})


class Settings(BaseSettings):
    env: str = "development"

    database_url_sync: str = "postgresql://localhost:5432/vocab_qc"
    db_echo: bool = False

    ai_api_key: str = ""
    ai_api_base_url: str = ""
    ai_model: str = "gemini-3-flash-preview"
    ai_max_concurrency: int = 20
    ai_max_retries: int = 3
    ai_task_timeout: int = 360
    ai_use_proxy: bool = False  # True=使用系统代理（GPT等海外API），False=直连（豆包等国内API）
    ai_gateway_mode: bool = False  # True=51talk AI Gateway 格式（api_key 在 body，响应包裹在 res 中）
    ai_gateway_provider: str = "OPENAI"  # Gateway provider: OPENAI/GEMINI/AZURE/DEEPSEEK 等
    ai_gateway_biz_type: str = "vocab_qc"  # Gateway biz_type 标识
    ai_gateway_async: bool = False  # True=使用异步提交+轮询（仅 ai_gateway_mode=True 时生效）
    ai_gateway_poll_interval: float = 3.0  # 轮询间隔（秒）
    ai_gateway_poll_max_wait: int = 300  # 单任务最大轮询等待（秒）
    allow_private_ai_url: bool = False

    max_regenerate_retries: int = 3
    max_upload_size_mb: int = 10

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 4

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


def validate_production_config() -> None:
    """生产环境启动时校验关键安全配置。"""
    if settings.env != "production":
        return

    errors: list[str] = []

    if len(settings.jwt_secret_key.encode()) < 32:
        errors.append("VOCAB_QC_JWT_SECRET_KEY 长度不足（HS256 要求 ≥32 字节）")

    if not settings.ai_api_key:
        errors.append("VOCAB_QC_AI_API_KEY 未配置")

    if not settings.ai_api_base_url:
        errors.append("VOCAB_QC_AI_API_BASE_URL 未配置")

    if "sqlite" in settings.database_url_sync.lower():
        errors.append("生产环境禁止使用 SQLite 数据库")

    if settings.db_echo:
        errors.append("生产环境禁止 VOCAB_QC_DB_ECHO=True（性能风险）")

    if not settings.allowed_email_domains:
        errors.append("VOCAB_QC_ALLOWED_EMAIL_DOMAINS 不能为空")

    if any(("localhost" in o or o == "*") for o in settings.cors_origins):
        errors.append("VOCAB_QC_CORS_ORIGINS 不能包含 localhost 或 *")

    if settings.jwt_expire_hours > 4:
        errors.append(f"VOCAB_QC_JWT_EXPIRE_HOURS={settings.jwt_expire_hours} 建议 ≤4")

    if settings.allow_private_ai_url:
        errors.append("生产环境禁止 VOCAB_QC_ALLOW_PRIVATE_AI_URL=True（SSRF 风险）")

    if settings.ai_gateway_async and not settings.ai_gateway_mode:
        errors.append("VOCAB_QC_AI_GATEWAY_ASYNC=True 需要 VOCAB_QC_AI_GATEWAY_MODE=True")
    if settings.ai_gateway_async and settings.ai_task_timeout < settings.ai_gateway_poll_max_wait:
        errors.append(
            f"ai_task_timeout({settings.ai_task_timeout}) 应 >= ai_gateway_poll_max_wait({settings.ai_gateway_poll_max_wait})"
        )

    if not settings.smtp_host:
        errors.append("VOCAB_QC_SMTP_HOST 未配置，无法发送验证码")

    if errors:
        raise RuntimeError(
            "生产环境配置校验失败:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    logger.info(
        "安全配置摘要: env=%s, email_domains=%s, cors=%d个域名, jwt_expire=%dh",
        settings.env,
        settings.allowed_email_domains,
        len(settings.cors_origins),
        settings.jwt_expire_hours,
    )
