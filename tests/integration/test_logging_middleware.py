"""日志中间件集成测试: RequestIdMiddleware + AccessLogMiddleware."""

import logging
import time

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from vocab_qc.core.logging_config import (
    AccessLogMiddleware,
    RequestIdMiddleware,
    _request_id_var,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_request_id():
    """每个测试前后重置 request_id."""
    token = _request_id_var.set("-")
    yield
    _request_id_var.reset(token)


def _create_app(slow_ms: int = 3000) -> FastAPI:
    """创建带中间件的测试应用."""
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware, slow_ms=slow_ms)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/test")
    def test_endpoint():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/slow")
    def slow_endpoint():
        time.sleep(0.05)
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# RequestIdMiddleware
# ---------------------------------------------------------------------------

class TestRequestIdMiddleware:

    def test_generates_request_id_in_response(self):
        client = TestClient(_create_app())
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        rid = resp.headers["X-Request-ID"]
        assert len(rid) == 8  # UUID hex[:8]

    def test_uses_provided_request_id(self):
        client = TestClient(_create_app())
        resp = client.get("/test", headers={"X-Request-ID": "custom-id-999"})
        assert resp.headers["X-Request-ID"] == "custom-id-999"

    def test_different_requests_get_different_ids(self):
        client = TestClient(_create_app())
        r1 = client.get("/test")
        r2 = client.get("/test")
        id1 = r1.headers["X-Request-ID"]
        id2 = r2.headers["X-Request-ID"]
        assert id1 != id2


# ---------------------------------------------------------------------------
# AccessLogMiddleware
# ---------------------------------------------------------------------------

class TestAccessLogMiddleware:

    def test_logs_request(self, caplog):
        client = TestClient(_create_app())
        with caplog.at_level(logging.INFO, logger="vocab_qc.access"):
            client.get("/test")

        records = [r for r in caplog.records if r.name == "vocab_qc.access"]
        assert len(records) == 1
        msg = records[0].message
        assert "GET" in msg
        assert "/test" in msg
        assert "200" in msg
        assert "ms" in msg

    def test_skips_health_endpoint(self, caplog):
        client = TestClient(_create_app())
        with caplog.at_level(logging.INFO, logger="vocab_qc.access"):
            client.get("/health")

        records = [r for r in caplog.records if r.name == "vocab_qc.access"]
        assert len(records) == 0

    def test_slow_request_warning(self, caplog):
        # slow_ms=30 使 50ms 的 /slow 端点触发慢请求
        client = TestClient(_create_app(slow_ms=30))
        with caplog.at_level(logging.WARNING, logger="vocab_qc.access"):
            client.get("/slow")

        warnings = [r for r in caplog.records if r.name == "vocab_qc.access" and r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "[SLOW]" in warnings[0].message

    def test_normal_request_info_level(self, caplog):
        client = TestClient(_create_app())
        with caplog.at_level(logging.INFO, logger="vocab_qc.access"):
            client.get("/test")

        records = [r for r in caplog.records if r.name == "vocab_qc.access"]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO
        assert "[SLOW]" not in records[0].message

    def test_logs_client_ip(self, caplog):
        client = TestClient(_create_app())
        with caplog.at_level(logging.INFO, logger="vocab_qc.access"):
            client.get("/test")

        records = [r for r in caplog.records if r.name == "vocab_qc.access"]
        assert "client=" in records[0].message
