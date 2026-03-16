"""Gateway 异步轮询模式测试."""

from itertools import count
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from vocab_qc.core.generators.base import (
    AiRequestError,
    build_ai_request,
    build_poll_body,
    parse_async_submit_response,
    parse_poll_response,
    poll_gateway_task_async,
    poll_gateway_task_sync,
)

# ── parse_async_submit_response ──


class TestParseAsyncSubmitResponse:
    def test_success(self):
        task_no = parse_async_submit_response({"code": 10000, "res": "task_abc_123"})
        assert task_no == "task_abc_123"

    def test_bad_code(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_async_submit_response({"code": 50000, "res": "task_abc"})
        assert exc_info.value.error_type == "task_submit_failed"

    def test_res_not_string(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_async_submit_response({"code": 10000, "res": {"some": "dict"}})
        assert exc_info.value.error_type == "task_submit_failed"

    def test_res_none(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_async_submit_response({"code": 10000, "res": None})
        assert exc_info.value.error_type == "task_submit_failed"


# ── parse_poll_response ──


class TestParsePollResponse:
    def test_completed(self):
        data = {"code": 10000, "res": {
            "status": "COMPLETED",
            "result": {"choices": [{"message": {"content": "hi"}}]},
            "failed_reason": "",
        }}
        status, result, reason = parse_poll_response(data)
        assert status == "COMPLETED"
        assert result == {"choices": [{"message": {"content": "hi"}}]}
        assert reason == ""

    def test_pending(self):
        status, result, reason = parse_poll_response(
            {"code": 10000, "res": {"status": "PENDING", "failed_reason": ""}}
        )
        assert status == "PENDING"
        assert result is None

    def test_failed(self):
        status, result, reason = parse_poll_response(
            {"code": 10000, "res": {"status": "FAILED", "failed_reason": "model overloaded"}}
        )
        assert status == "FAILED"
        assert reason == "model overloaded"

    def test_bad_code(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_poll_response({"code": 50000, "res": {"status": "COMPLETED"}})
        assert exc_info.value.error_type == "task_poll_error"

    def test_res_none(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_poll_response({"code": 10000, "res": None})
        assert exc_info.value.error_type == "task_poll_error"

    def test_missing_status(self):
        with pytest.raises(AiRequestError) as exc_info:
            parse_poll_response({"code": 10000, "res": {"result": {}}})
        assert exc_info.value.error_type == "task_poll_error"


# ── build_poll_body ──


class TestBuildPollBody:
    def test_preserves_biz_id(self):
        submit_body = {
            "provider": "VERTEX",
            "model": "gemini-3-flash-preview",
            "api_key": "sk-xxx",
            "biz_type": "vocab_qc",
            "biz_id": "uuid-1234",
            "stream": False,
            "async": True,
            "messages": [],
        }
        poll_body = build_poll_body(submit_body, "task_999")
        assert poll_body["biz_id"] == "uuid-1234"
        assert poll_body["task_no"] == "task_999"
        assert poll_body["provider"] == "VERTEX"
        assert poll_body["model"] == "gemini-3-flash-preview"
        assert "messages" not in poll_body
        assert "stream" not in poll_body


# ── build_ai_request with async flag ──


class TestBuildAiRequestAsyncFlag:
    @patch("vocab_qc.core.generators.base.settings")
    def test_async_true_when_enabled(self, mock_settings):
        mock_settings.ai_gateway_mode = True
        mock_settings.ai_gateway_async = True
        mock_settings.ai_gateway_biz_type = "vocab_qc"
        mock_settings.ai_gateway_provider = "OPENAI"
        _, _, body = build_ai_request(
            "https://gw.example.com/v1", "key", "gpt-4", "sys", "user",
        )
        assert body["async"] is True

    @patch("vocab_qc.core.generators.base.settings")
    def test_async_false_when_disabled(self, mock_settings):
        mock_settings.ai_gateway_mode = True
        mock_settings.ai_gateway_async = False
        mock_settings.ai_gateway_biz_type = "vocab_qc"
        mock_settings.ai_gateway_provider = "OPENAI"
        _, _, body = build_ai_request(
            "https://gw.example.com/v1", "key", "gpt-4", "sys json", "user",
        )
        assert body["async"] is False

    @patch("vocab_qc.core.generators.base.settings")
    def test_no_async_field_for_standard_mode(self, mock_settings):
        mock_settings.ai_gateway_mode = False
        _, _, body = build_ai_request(
            "https://api.openai.com/v1", "key", "gpt-4", "sys json", "user",
        )
        assert "async" not in body


# ── poll_gateway_task_async ──


def _make_poll_response(status, result=None, failed_reason=""):
    """构造 httpx.Response 的 mock（轮询响应）。"""
    data = {"code": 10000, "res": {
        "status": status,
        "result": result,
        "failed_reason": failed_reason,
    }}
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = data
    resp.text = ""
    return resp


_SUBMIT_BODY = {
    "provider": "VERTEX",
    "model": "gemini-3-flash-preview",
    "api_key": "sk-xxx",
    "biz_type": "vocab_qc",
    "biz_id": "uuid-1234",
}

_COMPLETED_RESULT = {"choices": [{"message": {"content": '{"ok": true}'}}]}


class TestPollGatewayTaskAsync:
    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_immediate_completed(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_poll_response("COMPLETED", _COMPLETED_RESULT)

        result = await poll_gateway_task_async(client, "https://gw/v1", "t1", _SUBMIT_BODY)
        assert result == _COMPLETED_RESULT
        assert client.post.call_count == 1

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_pending_then_completed(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        responses = iter([
            _make_poll_response("PENDING"),
            _make_poll_response("PROCESSING"),
            _make_poll_response("COMPLETED", _COMPLETED_RESULT),
        ])
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = lambda *a, **kw: next(responses)

        result = await poll_gateway_task_async(client, "https://gw/v1", "t2", _SUBMIT_BODY)
        assert result == _COMPLETED_RESULT
        assert client.post.call_count == 3

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_task_failed(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_poll_response("FAILED", failed_reason="model error")

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t3", _SUBMIT_BODY)
        assert exc_info.value.error_type == "task_failed"
        assert exc_info.value.task_no == "t3"
        assert "model error" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_poll_timeout(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 0.02  # 极短超时

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = _make_poll_response("PENDING")

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t4", _SUBMIT_BODY)
        assert exc_info.value.error_type == "task_timeout"
        assert exc_info.value.task_no == "t4"

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_poll_network_timeout(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = httpx.TimeoutException("read timed out")

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t5", _SUBMIT_BODY)
        assert exc_info.value.error_type == "timeout"
        assert exc_info.value.task_no == "t5"

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_poll_http_error(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 502
        resp.text = "Bad Gateway"
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = resp

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t6", _SUBMIT_BODY)
        assert exc_info.value.error_type == "http_error"
        assert exc_info.value.status_code == 502
        assert exc_info.value.task_no == "t6"

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_poll_response_bad_code(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {"code": 50000, "res": None}
        resp.text = ""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = resp

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t7", _SUBMIT_BODY)
        assert exc_info.value.error_type == "task_poll_error"

    @pytest.mark.asyncio
    @patch("vocab_qc.core.generators.base.settings")
    async def test_poll_connect_error(self, mock_settings):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(AiRequestError) as exc_info:
            await poll_gateway_task_async(client, "https://gw/v1", "t8", _SUBMIT_BODY)
        assert exc_info.value.error_type == "connect_error"
        assert exc_info.value.task_no == "t8"


# ── poll_gateway_task_sync ──


class TestPollGatewayTaskSync:
    @patch("vocab_qc.core.generators.base.time")
    @patch("vocab_qc.core.generators.base.settings")
    def test_immediate_completed(self, mock_settings, mock_time):
        mock_settings.ai_gateway_poll_interval = 0.01
        mock_settings.ai_gateway_poll_max_wait = 5
        # monotonic: start=0, deadline check=1, post=2, ...
        mock_time.monotonic.side_effect = count(0, 1).__next__
        mock_time.sleep = MagicMock()

        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {"code": 10000, "res": {
            "status": "COMPLETED", "result": _COMPLETED_RESULT, "failed_reason": "",
        }}
        resp.text = ""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = resp

        result = poll_gateway_task_sync(client, "https://gw/v1", "t1", _SUBMIT_BODY)
        assert result == _COMPLETED_RESULT


# ── AiRequestError.task_no ──


class TestAiRequestErrorTaskNo:
    def test_task_no_attribute(self):
        err = AiRequestError("task_failed", detail="xxx", task_no="t99")
        assert err.task_no == "t99"

    def test_task_no_default_empty(self):
        err = AiRequestError("timeout")
        assert err.task_no == ""


# ── Config 校验 ──


class TestConfigValidation:
    @patch("vocab_qc.core.config.settings")
    def test_async_without_gateway_mode(self, mock_settings):
        from vocab_qc.core.config import validate_production_config
        mock_settings.env = "production"
        mock_settings.ai_gateway_async = True
        mock_settings.ai_gateway_mode = False
        mock_settings.ai_task_timeout = 360
        mock_settings.ai_gateway_poll_max_wait = 300
        mock_settings.jwt_secret_key = "a" * 32
        mock_settings.ai_api_key = "key"
        mock_settings.ai_api_base_url = "https://gw"
        mock_settings.database_url_sync = "postgresql://x"
        mock_settings.db_echo = False
        mock_settings.allowed_email_domains = ["51talk.com"]
        mock_settings.cors_origins = ["https://app.51talk.com"]
        mock_settings.jwt_expire_hours = 4
        mock_settings.allow_private_ai_url = False
        mock_settings.smtp_host = "smtp.51talk.com"

        with pytest.raises(RuntimeError, match="AI_GATEWAY_ASYNC.*AI_GATEWAY_MODE"):
            validate_production_config()

    @patch("vocab_qc.core.config.settings")
    def test_timeout_less_than_poll_max(self, mock_settings):
        from vocab_qc.core.config import validate_production_config
        mock_settings.env = "production"
        mock_settings.ai_gateway_async = True
        mock_settings.ai_gateway_mode = True
        mock_settings.ai_task_timeout = 100
        mock_settings.ai_gateway_poll_max_wait = 300
        mock_settings.jwt_secret_key = "a" * 32
        mock_settings.ai_api_key = "key"
        mock_settings.ai_api_base_url = "https://gw"
        mock_settings.database_url_sync = "postgresql://x"
        mock_settings.db_echo = False
        mock_settings.allowed_email_domains = ["51talk.com"]
        mock_settings.cors_origins = ["https://app.51talk.com"]
        mock_settings.jwt_expire_hours = 4
        mock_settings.allow_private_ai_url = False
        mock_settings.smtp_host = "smtp.51talk.com"

        with pytest.raises(RuntimeError, match="ai_task_timeout.*ai_gateway_poll_max_wait"):
            validate_production_config()
