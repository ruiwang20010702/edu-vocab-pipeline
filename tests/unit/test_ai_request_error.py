"""AiRequestError 结构化异常 + classify_ai_error 增强测试."""

import asyncio

import pytest

from vocab_qc.core.generators.base import AiRequestError
from vocab_qc.core.models.quality_layer import classify_ai_error


class TestAiRequestError:
    """AiRequestError 各类型构造与 format_message."""

    def test_timeout(self):
        err = AiRequestError("timeout", elapsed_ms=3200, detail="read timed out")
        assert err.error_type == "timeout"
        assert err.elapsed_ms == 3200
        assert err.status_code is None
        assert "timeout" in str(err)
        assert "3200ms" in str(err)
        assert "read timed out" in str(err)

    def test_http_error(self):
        err = AiRequestError(
            "http_error",
            status_code=429,
            response_body='{"error": "rate limited"}',
            elapsed_ms=150,
        )
        assert err.error_type == "http_error"
        assert err.status_code == 429
        assert "HTTP 429" in str(err)
        assert "150ms" in str(err)
        assert "rate limited" in str(err)

    def test_connect_error(self):
        err = AiRequestError("connect_error", elapsed_ms=50, detail="connection refused")
        assert err.error_type == "connect_error"
        assert "connection refused" in str(err)

    def test_parse_error(self):
        err = AiRequestError(
            "parse_error",
            elapsed_ms=800,
            response_body="not json at all",
            detail="Expecting value",
        )
        assert err.error_type == "parse_error"
        # response_body 优先于 detail
        assert "not json at all" in str(err)

    def test_format_truncates_long_body(self):
        long_body = "x" * 500
        err = AiRequestError("http_error", status_code=500, response_body=long_body)
        # _format_message 截断到 200 字符
        msg = str(err)
        # 200 chars of body + prefix parts
        assert len(long_body[:200]) <= len(msg)

    def test_minimal(self):
        err = AiRequestError("unknown")
        assert str(err) == "unknown"
        assert err.status_code is None
        assert err.response_body == ""
        assert err.elapsed_ms == 0
        assert err.task_no == ""

    def test_task_submit_failed(self):
        err = AiRequestError("task_submit_failed", detail="code=50000")
        assert err.error_type == "task_submit_failed"
        assert "code=50000" in str(err)

    def test_task_timeout(self):
        err = AiRequestError("task_timeout", detail="轮询超时(300s)", task_no="t123")
        assert err.error_type == "task_timeout"
        assert err.task_no == "t123"
        assert "轮询超时" in str(err)

    def test_task_failed(self):
        err = AiRequestError("task_failed", detail="model overloaded", task_no="t456")
        assert err.error_type == "task_failed"
        assert err.task_no == "t456"

    def test_task_poll_error(self):
        err = AiRequestError("task_poll_error", detail="code=50000, res=None")
        assert err.error_type == "task_poll_error"


class TestClassifyAiError:
    """classify_ai_error 增强：优先检查异常类型。"""

    def test_ai_request_error_direct(self):
        err = AiRequestError("http_error", status_code=502)
        assert classify_ai_error(err) == "http_error"

    def test_ai_request_error_timeout(self):
        err = AiRequestError("timeout")
        assert classify_ai_error(err) == "timeout"

    def test_ai_request_error_parse(self):
        err = AiRequestError("parse_error")
        assert classify_ai_error(err) == "parse_error"

    def test_asyncio_timeout_error(self):
        err = asyncio.TimeoutError()
        assert classify_ai_error(err) == "timeout"

    def test_fallback_timeout_string(self):
        err = RuntimeError("request timed out after 60s")
        assert classify_ai_error(err) == "timeout"

    def test_fallback_parse_string(self):
        err = ValueError("json decode error")
        assert classify_ai_error(err) == "parse_error"

    def test_fallback_http_string(self):
        err = RuntimeError("http connection failed")
        assert classify_ai_error(err) == "http_error"

    def test_fallback_unknown(self):
        err = RuntimeError("something completely different")
        assert classify_ai_error(err) == "unknown"

    def test_task_submit_failed(self):
        err = AiRequestError("task_submit_failed")
        assert classify_ai_error(err) == "task_submit_failed"

    def test_task_timeout(self):
        err = AiRequestError("task_timeout", task_no="t1")
        assert classify_ai_error(err) == "task_timeout"

    def test_task_failed(self):
        err = AiRequestError("task_failed", task_no="t2")
        assert classify_ai_error(err) == "task_failed"

    def test_task_poll_error(self):
        err = AiRequestError("task_poll_error")
        assert classify_ai_error(err) == "task_poll_error"
