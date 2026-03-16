"""AiClient 重试逻辑测试."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.ai_base import AiClient, AiRuleChecker


@pytest.fixture(autouse=True)
def _disable_gateway(monkeypatch):
    """测试中禁用 Gateway 模式，使用标准 OpenAI 响应格式。"""
    from vocab_qc.core import config
    monkeypatch.setattr(config.settings, "ai_gateway_mode", False)
    monkeypatch.setattr(config.settings, "ai_gateway_async", False)

# ---------------------------------------------------------------------------
# 辅助：构建标准 httpx response mock
# ---------------------------------------------------------------------------


def make_response(payload: dict, status_code: int = 200) -> MagicMock:
    content = json.dumps(payload)
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    resp.raise_for_status = MagicMock()
    return resp


def make_http_error_response() -> MagicMock:
    import httpx
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    return resp


# ---------------------------------------------------------------------------
# 占位模式（无 API key / base_url）
# ---------------------------------------------------------------------------


class TestAiClientPlaceholderMode:
    @pytest.mark.asyncio
    async def test_returns_passed_true_without_api_config(self):
        client = AiClient(api_key="", base_url="", model="gpt-4")
        result = await client.check("system", "user")
        assert result["passed"] is True
        assert "占位模式" in result["detail"]

    @pytest.mark.asyncio
    async def test_placeholder_when_api_key_none(self):
        AiClient(api_key=None, base_url=None, model=None)
        # 无 key 和 url，走占位分支
        with patch("vocab_qc.core.qc.layer2.ai_base.settings") as mock_settings:
            mock_settings.ai_api_key = ""
            mock_settings.ai_api_base_url = ""
            mock_settings.ai_model = "gpt-4"
            c = AiClient(api_key="", base_url="", model="gpt-4")
            result = await c.check("sys", "usr")
        assert result["passed"] is True


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


class TestAiClientSuccess:
    @pytest.mark.asyncio
    async def test_single_call_success(self):
        payload = {"passed": True, "detail": "all good"}
        mock_post = AsyncMock(return_value=make_response(payload))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = mock_post
            mock_cls.return_value = mock_http

            client = AiClient(api_key="sk-test", base_url="https://api.test.com", model="gpt-4", max_retries=3)
            result = await client.check("system prompt", "user prompt")

        assert result["passed"] is True
        assert result["detail"] == "all good"
        mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_json_parsed_correctly(self):
        payload = {"custom_key": "custom_value", "passed": False}
        mock_post = AsyncMock(return_value=make_response(payload))

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = mock_post
            mock_cls.return_value = mock_http

            client = AiClient(api_key="sk-x", base_url="https://x.com", model="m")
            result = await client.check("sys", "usr")

        assert result["custom_key"] == "custom_value"
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# 重试路径：失败后重试成功
# ---------------------------------------------------------------------------


class TestAiClientRetryThenSuccess:
    @pytest.mark.asyncio
    async def test_fails_twice_then_succeeds(self):
        success_payload = {"passed": True, "detail": "ok"}
        success_resp = make_response(success_payload)

        fail_resp = MagicMock()
        import httpx
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503", request=MagicMock(), response=MagicMock()
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.HTTPStatusError("503", request=MagicMock(), response=MagicMock())
            return success_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=side_effect)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=3)
                result = await client.check("sys", "usr")

        assert result["passed"] is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_fails_once_then_succeeds(self):
        success_payload = {"passed": True}
        success_resp = make_response(success_payload)
        attempts = []

        async def side_effect(*args, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("first attempt fails")
            return success_resp

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=side_effect)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=3)
                result = await client.check("sys", "usr")

        assert result["passed"] is True
        assert len(attempts) == 2


# ---------------------------------------------------------------------------
# 全部失败路径：抛出 RuntimeError
# ---------------------------------------------------------------------------


class TestAiClientAllRetriesFail:
    @pytest.mark.asyncio
    async def test_raises_runtime_error_after_all_retries(self):
        async def always_fail(*args, **kwargs):
            raise ConnectionError("permanent failure")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=always_fail)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=3)
                with pytest.raises(RuntimeError) as exc_info:
                    await client.check("sys", "usr")

        assert "3次重试后" in str(exc_info.value)
        assert "permanent failure" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retry_count_matches_max_retries(self):
        call_count = 0

        async def count_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=count_calls)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=2)
                with pytest.raises(RuntimeError):
                    await client.check("sys", "usr")

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_runtime_error_message_contains_attempt_count(self):
        async def fail(*args, **kwargs):
            raise ValueError("bad json")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=fail)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=5)
                with pytest.raises(RuntimeError) as exc_info:
                    await client.check("sys", "usr")

        assert "5次重试后" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 指数退避：验证 asyncio.sleep 调用
# ---------------------------------------------------------------------------


class TestAiClientBackoff:
    @pytest.mark.asyncio
    async def test_exponential_backoff_sleep_called_between_retries(self):
        async def fail(*args, **kwargs):
            raise ConnectionError("fail")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(side_effect=fail)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=3)
                with pytest.raises(RuntimeError):
                    await client.check("sys", "usr")

        # 3次重试：第0次失败 sleep(1)，第1次失败 sleep(2)，第2次失败不 sleep
        assert mock_sleep.call_count == 2
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args == [1, 2]  # 2**0, 2**1

    @pytest.mark.asyncio
    async def test_no_sleep_on_first_successful_call(self):
        success_resp = make_response({"passed": True})

        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.post = AsyncMock(return_value=success_resp)
            mock_cls.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                client = AiClient(api_key="sk-x", base_url="https://x.com", model="m", max_retries=3)
                await client.check("sys", "usr")

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# AiRuleChecker 基类：check 方法错误处理
# ---------------------------------------------------------------------------


class ConcreteRuleChecker(AiRuleChecker):
    rule_id = "TEST_RULE"
    dimension = "test"
    system_prompt = "test system"

    def build_user_prompt(self, content, word, meaning=None, **kwargs):
        return f"word={word} content={content}"


class TestAiRuleChecker:
    @pytest.mark.asyncio
    async def test_returns_rule_result_on_success(self):
        mock_client = MagicMock()
        mock_client.check = AsyncMock(return_value={"passed": True, "detail": "looks good"})

        checker = ConcreteRuleChecker()
        result = await checker.check(mock_client, content="test content", word="test")

        assert isinstance(result, RuleResult)
        assert result.rule_id == "TEST_RULE"
        assert result.passed is True
        assert result.detail == "looks good"

    @pytest.mark.asyncio
    async def test_returns_failed_rule_result_on_exception(self):
        mock_client = MagicMock()
        mock_client.check = AsyncMock(side_effect=RuntimeError("network error"))

        checker = ConcreteRuleChecker()
        result = await checker.check(mock_client, content="x", word="x")

        assert result.rule_id == "TEST_RULE"
        assert result.passed is False
        assert "AI 调用失败" in result.detail

    @pytest.mark.asyncio
    async def test_passed_false_when_key_missing(self):
        mock_client = MagicMock()
        mock_client.check = AsyncMock(return_value={})  # 无 passed 字段

        checker = ConcreteRuleChecker()
        result = await checker.check(mock_client, content="x", word="x")

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_meaning_forwarded_to_build_user_prompt(self):
        captured = {}

        class TrackingChecker(AiRuleChecker):
            rule_id = "T1"
            system_prompt = "sys"

            def build_user_prompt(self, content, word, meaning=None, **kwargs):
                captured["meaning"] = meaning
                return "prompt"

        mock_client = MagicMock()
        mock_client.check = AsyncMock(return_value={"passed": True})

        checker = TrackingChecker()
        await checker.check(mock_client, content="x", word="x", meaning="含义")

        assert captured["meaning"] == "含义"
