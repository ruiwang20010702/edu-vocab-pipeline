"""日志配置: 统一格式、请求追踪、访问日志、耗时统计."""

import contextvars
import json
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ---------------------------------------------------------------------------
# request_id 上下文变量
# ---------------------------------------------------------------------------

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-",
)


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(rid: str) -> contextvars.Token[str]:
    """手动设置 request_id（后台任务使用）."""
    return _request_id_var.set(rid)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

# 不需要序列化到 JSON extra 的标准 LogRecord 属性
_BUILTIN_ATTRS = frozenset({
    "name", "msg", "args", "created", "relativeCreated", "exc_info",
    "exc_text", "stack_info", "lineno", "funcName", "pathname", "filename",
    "module", "thread", "threadName", "process", "processName", "levelname",
    "levelno", "message", "asctime", "msecs", "taskName",
    # 自定义注入的
    "request_id",
})


class JsonFormatter(logging.Formatter):
    """单行 JSON 日志格式（生产环境用）."""

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()

        log_obj: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
            "request_id": getattr(record, "request_id", "-"),
        }

        # 附加 extra 字段
        for key, val in record.__dict__.items():
            if key not in _BUILTIN_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(val)
                    log_obj[key] = val
                except (TypeError, ValueError):
                    log_obj[key] = str(val)

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            log_obj["exception"] = record.exc_text

        return json.dumps(log_obj, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """可读文本日志格式（开发环境用）."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return super().format(record)


# ---------------------------------------------------------------------------
# Filter: 注入 request_id 到每条 LogRecord
# ---------------------------------------------------------------------------

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


# ---------------------------------------------------------------------------
# Middleware: 请求 ID 注入
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """从请求头读取或生成 request_id，写入 contextvars 和响应头."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        token = _request_id_var.set(rid)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            _request_id_var.reset(token)


# ---------------------------------------------------------------------------
# Middleware: 访问日志
# ---------------------------------------------------------------------------

_access_logger = logging.getLogger("vocab_qc.access")

# 不记录访问日志的路径
_SKIP_PATHS = frozenset({"/health"})


class AccessLogMiddleware(BaseHTTPMiddleware):
    """记录每个 HTTP 请求的方法、路径、状态码、耗时."""

    def __init__(self, app, slow_ms: int = 3000) -> None:  # noqa: ANN001
        super().__init__(app)
        self.slow_ms = slow_ms

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        t0 = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        client = request.client.host if request.client else "-"
        level = logging.WARNING if elapsed_ms > self.slow_ms else logging.INFO
        suffix = " [SLOW]" if elapsed_ms > self.slow_ms else ""

        _access_logger.log(
            level,
            "%s %s %d %dms client=%s%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            client,
            suffix,
        )
        return response


# ---------------------------------------------------------------------------
# 耗时统计上下文管理器
# ---------------------------------------------------------------------------

@contextmanager
def log_elapsed(
    logger: logging.Logger,
    msg: str,
    level: int = logging.INFO,
) -> Generator[None, None, None]:
    """记录代码块耗时.

    用法::

        with log_elapsed(logger, "Layer1 质检"):
            runner.run(...)
    """
    t0 = time.monotonic()
    yield
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.log(level, "%s elapsed=%dms", msg, elapsed_ms)


# ---------------------------------------------------------------------------
# 初始化函数: 供 main.py 调用
# ---------------------------------------------------------------------------

def configure_logging(log_format: str = "text", log_level: str = "INFO") -> None:
    """配置 root logger 的 Formatter 和 Filter.

    应在 ``_setup_async_logging()`` **之前** 调用，
    这样 QueueHandler 转发的 LogRecord 已带有 request_id。
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 注入 request_id filter
    root.addFilter(RequestIdFilter())

    # 确保至少有一个 StreamHandler（gunicorn worker 下可能没有）
    if not root.handlers:
        root.addHandler(logging.StreamHandler())

    # 设置 formatter
    formatter = JsonFormatter() if log_format == "json" else TextFormatter()
    for handler in root.handlers:
        handler.setFormatter(formatter)
