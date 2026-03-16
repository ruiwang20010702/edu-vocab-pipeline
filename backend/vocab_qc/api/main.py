"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from sqlalchemy.orm import Session

from vocab_qc.core.config import _INSECURE_JWT_SECRETS, settings, validate_production_config
from vocab_qc.api.deps import get_db
from vocab_qc.api.routers import admin, auth, batch, export, import_, prompt, qc, review, stats, words

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    if settings.jwt_secret_key in _INSECURE_JWT_SECRETS:
        if settings.env == "production":
            raise RuntimeError(
                "生产环境禁止使用默认 JWT 密钥！"
                "请设置环境变量 VOCAB_QC_JWT_SECRET_KEY"
            )
        logger.warning("JWT_SECRET_KEY 使用默认值，仅适用于开发环境")

    validate_production_config()

    # PM-H3: 启动时自动同步 Prompt 文件 → DB
    try:
        from vocab_qc.core.db import SyncSessionLocal
        from vocab_qc.core.services import prompt_service
        with SyncSessionLocal() as session:
            result = prompt_service.sync_prompts(session)
            session.commit()
            logger.info("Prompt 同步完成: %s", result)
    except Exception:
        logger.warning("Prompt 启动同步失败（不阻塞启动）", exc_info=True)

    # 预热词根词缀知识库缓存，避免首次请求延迟
    try:
        from vocab_qc.core.generators.morpheme_kb import get_morpheme_kb
        kb = get_morpheme_kb()
        logger.info("词根词缀知识库预热完成: %d 条", len(kb))
    except Exception:
        logger.warning("词根词缀知识库预热失败（不阻塞启动）", exc_info=True)

    yield

    # --- shutdown: 关闭共享 HTTP 客户端 ---
    try:
        from vocab_qc.core.generators.base import close_http_clients
        await close_http_clients()
    except Exception:
        logger.warning("关闭 HTTP 客户端失败", exc_info=True)


_docs_kwargs = (
    {"docs_url": None, "redoc_url": None, "openapi_url": None}
    if settings.env == "production"
    else {}
)
app = FastAPI(title="词汇质检系统 V2.0", version="0.1.0", lifespan=lifespan, **_docs_kwargs)

# 速率限制（全局 + 路由级）
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(admin.user_router)
app.include_router(stats.router)
app.include_router(words.router)
app.include_router(import_.router)
app.include_router(qc.router)
app.include_router(review.router)
app.include_router(batch.router)
app.include_router(export.router)
app.include_router(prompt.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """健康检查（含数据库探测）。"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "degraded"}
