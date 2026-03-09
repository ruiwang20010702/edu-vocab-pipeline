"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from vocab_qc.core.config import _INSECURE_JWT_SECRETS, settings
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
    yield
    # --- shutdown ---


app = FastAPI(title="词汇质检系统 V2.0", version="0.1.0", lifespan=lifespan)

# 速率限制
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(stats.router)
app.include_router(words.router)
app.include_router(import_.router)
app.include_router(qc.router)
app.include_router(review.router)
app.include_router(batch.router)
app.include_router(export.router)
app.include_router(prompt.router)


@app.get("/health")
def health():
    return {"status": "ok"}
