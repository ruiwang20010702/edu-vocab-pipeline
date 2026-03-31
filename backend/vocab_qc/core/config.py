"""应用配置."""

import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_INSECURE_JWT_SECRETS = frozenset({"dev-secret-change-in-production", "changeme", ""})


class Settings(BaseSettings):
    env: str = "development"

    database_url_sync: str = "postgresql://localhost:5432/vocab_qc"
    database_url_migrate: str = ""  # Alembic 迁移专用连接串（可选，env.py 单独读取）
    db_echo: bool = False

    ai_api_key: str = ""
    ai_api_base_url: str = ""
    ai_model: str = "gemini-3-flash-preview|efficiency"
    ai_max_concurrency: int = 20
    ai_request_stagger: float = 0.2  # 并发请求启动间隔（秒），0 表示不错开
    ai_max_retries: int = 3
    ai_task_timeout: int = 360
    ai_use_proxy: bool = False  # True=使用系统代理（GPT等海外API），False=直连（豆包等国内API）
    ai_gateway_mode: bool = True  # True=51talk AI Gateway 格式（api_key 在 body，响应包裹在 res 中）
    ai_gateway_provider: str = "OPENAI"  # Gateway provider: OPENAI/GEMINI/AZURE/DEEPSEEK 等
    ai_gateway_biz_type: str = "vocab_qc"  # Gateway biz_type 标识
    ai_gateway_async: bool = True  # True=使用异步提交+轮询（仅 ai_gateway_mode=True 时生效）
    ai_gateway_poll_interval: float = 3.0  # 轮询间隔（秒）
    ai_gateway_poll_max_wait: int = 600  # 单任务最大轮询等待（秒）
    allow_private_ai_url: bool = False
    allowed_ai_hosts: list[str] = []

    ai_circuit_breaker_threshold: int = 15  # 连续失败次数触发熔断
    ai_circuit_breaker_recovery: int = 30   # 熔断恢复冷却时间（秒）

    # 任务队列（提交/轮询解耦）
    ai_use_task_queue: bool = False         # 开关：True=新队列模式，False=原轮询模式
    ai_submit_batch_size: int = 20          # 每批提交数（匹配 Gateway 限制）
    ai_submit_stagger: float = 0.5          # 批次间提交间隔（秒），防 429
    ai_poll_pool_size: int = 50             # 轮询 worker 数
    ai_poll_scan_interval: float = 2.0      # 轮询扫描间隔（秒）

    # 回调模式（替代轮询，需 ai_use_task_queue=True）
    ai_callback_mode: bool = False              # 开关：True=回调主驱+轮询兜底
    ai_callback_url: str = ""                   # Gateway 回调地址
    ai_callback_allowed_ips: list[str] = []     # 回调来源 IP 白名单
    ai_callback_grace_period: float = 300.0     # 宽限期（秒），超时后降级为轮询
    ai_poll_callback_scan_interval: float = 30.0   # 回调模式下安全网扫描间隔（秒）
    ai_poll_stale_threshold_minutes: float = 10.0  # 回调模式下仅轮询提交超过此时间的任务

    production_batch_size: int = 50  # 大批量生产时每批处理的词数（fallback）
    production_max_items_per_batch: int = 500  # 智能分批：每批 ContentItem 数上限
    package_processing_timeout_hours: int = 6  # Package processing 状态超时（小时）

    max_regenerate_retries: int = 3
    max_upload_size_mb: int = 10

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 4

    # Cookie
    cookie_name: str = "access_token"
    cookie_secure: bool = False  # 生产环境通过环境变量设 True
    cookie_samesite: str = "lax"
    cookie_domain: str = ""  # 空=当前域名
    cookie_path: str = "/"

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # 认证
    allowed_email_domains: list[str] = []
    verification_code_expire_minutes: int = 10

    # 日志
    log_format: str = "text"         # "text" | "json"，生产环境设 "json"
    log_level: str = "INFO"          # DEBUG / INFO / WARNING / ERROR
    log_slow_request_ms: int = 3000  # 慢请求阈值（毫秒）

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = {"env_prefix": "VOCAB_QC_", "env_file": ".env"}

    @model_validator(mode="before")
    @classmethod
    def strip_whitespace(cls, values: dict) -> dict:
        """Gaea 平台注入的环境变量值末尾带换行符，统一 strip。"""
        return {k: v.strip() if isinstance(v, str) else v for k, v in values.items()}


settings = Settings()


def validate_production_config() -> None:
    """生产环境启动时校验关键安全配置。"""
    if settings.env not in ("production", "staging"):
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

    if not settings.cookie_secure:
        errors.append("VOCAB_QC_COOKIE_SECURE 必须为 True（生产环境需要 Secure Cookie）")

    if settings.allow_private_ai_url:
        errors.append("生产环境禁止 VOCAB_QC_ALLOW_PRIVATE_AI_URL=True（SSRF 风险）")

    if not settings.allowed_ai_hosts:
        errors.append("VOCAB_QC_ALLOWED_AI_HOSTS 不能为空（SSRF 防护需要白名单）")

    if settings.ai_gateway_async and not settings.ai_gateway_mode:
        errors.append("VOCAB_QC_AI_GATEWAY_ASYNC=True 需要 VOCAB_QC_AI_GATEWAY_MODE=True")
    if settings.ai_gateway_async and settings.ai_task_timeout < settings.ai_gateway_poll_max_wait:
        errors.append(
            f"ai_task_timeout({settings.ai_task_timeout})"
            f" 应 >= ai_gateway_poll_max_wait({settings.ai_gateway_poll_max_wait})"
        )

    if settings.ai_callback_mode:
        if not settings.ai_callback_url:
            errors.append("VOCAB_QC_AI_CALLBACK_MODE=True 时 VOCAB_QC_AI_CALLBACK_URL 不能为空")
        if not settings.ai_callback_allowed_ips:
            logger.warning("VOCAB_QC_AI_CALLBACK_ALLOWED_IPS 为空，回调端点不校验来源 IP（建议配置）")
        if not settings.ai_use_task_queue:
            errors.append("VOCAB_QC_AI_CALLBACK_MODE=True 需要 VOCAB_QC_AI_USE_TASK_QUEUE=True")

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
