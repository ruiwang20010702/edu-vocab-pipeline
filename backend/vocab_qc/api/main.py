"""FastAPI 应用入口."""

import logging
from contextlib import asynccontextmanager
from logging.handlers import QueueHandler, QueueListener
from queue import Queue

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from vocab_qc.api.deps import get_db
from vocab_qc.api.routers import admin, auth, batch, callback, export, import_, prompt, qc, review, stats, words
from vocab_qc.core.config import _INSECURE_JWT_SECRETS, settings, validate_production_config
from vocab_qc.core.logging_config import (
    AccessLogMiddleware,
    RequestIdMiddleware,
    configure_logging,
)

logger = logging.getLogger(__name__)


def _setup_async_logging() -> QueueListener:
    """将日志写入队列，后台线程异步消费，避免 I/O 阻塞请求线程。"""
    # 先配置格式和 Filter（在 QueueHandler 接管之前）
    configure_logging(log_format=settings.log_format, log_level=settings.log_level)

    log_queue: Queue = Queue(-1)
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    root.handlers = [QueueHandler(log_queue)]
    listener = QueueListener(log_queue, *original_handlers, respect_handler_level=True)
    listener.start()
    return listener


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    # 加大默认线程池：regenerate 的 L2 质检会通过 asyncio.to_thread 长时间占线程，
    # 默认 min(32, cpu+4) 在低 CPU 容器上太小，显式设为 16 保证并发余量
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=16))

    log_listener = _setup_async_logging()
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

    # 任务队列模式：恢复中断的任务 + 启动后台 polling pool
    # 使用文件锁确保多 worker 下只有一个 worker 启动 PollingPool
    _poll_task = None
    _lock_fd = None
    if settings.ai_use_task_queue:
        try:
            from vocab_qc.core.db import SyncSessionLocal
            from vocab_qc.core.polling_pool import PollingPool
            from vocab_qc.core.task_queue import TaskQueueService

            with SyncSessionLocal() as session:
                recovered = TaskQueueService.recover_interrupted(session)
                cleaned = TaskQueueService.cleanup_old(session)
                expired = TaskQueueService.fail_expired_tasks(session)
                session.commit()
                if recovered:
                    logger.info("恢复 %d 个中断的 AI 任务", recovered)
                if cleaned:
                    logger.info("清理 %d 条过期任务记录", cleaned)
                if expired:
                    logger.info("标记 %d 个超时任务为失败", expired)

            # 文件锁：只有获得锁的 worker 启动 PollingPool
            import fcntl
            _lock_fd = open("/tmp/.polling_pool.lock", "w")
            try:
                fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                pool = PollingPool.get_instance()
                import asyncio
                _poll_task = asyncio.create_task(pool.run_forever())
                logger.info("任务队列 PollingPool 已启动（当前 worker 持锁）")
            except BlockingIOError:
                logger.info("PollingPool 已由其他 worker 启动，跳过")
                _lock_fd.close()
                _lock_fd = None
        except Exception:
            logger.warning("PollingPool 启动失败（不阻塞启动）", exc_info=True)

    yield

    # --- shutdown ---
    # 停止 polling pool + 释放文件锁
    if settings.ai_use_task_queue and _poll_task is not None:
        try:
            from vocab_qc.core.polling_pool import PollingPool
            PollingPool.get_instance().shutdown()
            _poll_task.cancel()
            try:
                await _poll_task
            except asyncio.CancelledError:
                pass
            logger.info("PollingPool 已停止")
        except Exception:
            logger.warning("PollingPool 停止失败", exc_info=True)
        finally:
            if _lock_fd is not None:
                _lock_fd.close()

    try:
        from vocab_qc.core.generators.base import close_http_clients
        await close_http_clients()
    except Exception:
        logger.warning("关闭 HTTP 客户端失败", exc_info=True)

    log_listener.stop()


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
app.add_middleware(AccessLogMiddleware, slow_ms=settings.log_slow_request_ms)
app.add_middleware(RequestIdMiddleware)

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
app.include_router(callback.router)


@app.get("/health")
@auth.limiter.limit("30/minute")
def health(request: Request, db: Session = Depends(get_db)):
    """健康检查（含数据库探测）。"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "degraded"}
