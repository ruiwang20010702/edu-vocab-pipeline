"""Layer2 unified checkers mock 测试."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def make_client(return_value: dict) -> MagicMock:
    """构造一个 check 方法返回预设值的 AiClient mock."""
    client = MagicMock()
    client.check = AsyncMock(return_value=return_value)
    return client


def make_failing_client(exc: Exception) -> MagicMock:
    """构造一个 check 方法抛出异常的 AiClient mock."""
    client = MagicMock()
    client.check = AsyncMock(side_effect=exc)
    return client


# ---------------------------------------------------------------------------
# UnifiedSentenceChecker
# ---------------------------------------------------------------------------


class TestUnifiedSentenceChecker:
    checker = UnifiedSentenceChecker()

    @pytest.mark.asyncio
    async def test_returns_rule_results_for_all_rules(self):
        payload = {
            "results": [
                {"rule_id": "E1", "passed": True, "detail": "ok"},
                {"rule_id": "E2", "passed": True, "detail": "ok"},
                {"rule_id": "E3", "passed": True, "detail": "ok"},
                {"rule_id": "E4", "passed": True, "detail": "ok"},
                {"rule_id": "E5", "passed": True, "detail": "ok"},
                {"rule_id": "E8_AI", "passed": True, "detail": "ok"},
                {"rule_id": "E9", "passed": True, "detail": "ok"},
                {"rule_id": "E10", "passed": True, "detail": "ok"},
                {"rule_id": "E11", "passed": True, "detail": "ok"},
            ]
        }
        client = make_client(payload)
        results = await self.checker.check(
            client, content="She goes to school.", word="go", meaning="去", content_cn="她去上学。"
        )
        assert len(results) == 9
        assert all(isinstance(r, RuleResult) for r in results)

    @pytest.mark.asyncio
    async def test_failed_rule_propagated_correctly(self):
        payload = {
            "results": [
                {"rule_id": "E5", "passed": False, "detail": "包含倒装结构"},
            ]
        }
        client = make_client(payload)
        results = await self.checker.check(
            client, content="Never have I seen this.", word="never", meaning="从不"
        )
        assert len(results) == 1
        assert results[0].rule_id == "E5"
        assert results[0].passed is False
        assert "倒装" in results[0].detail

    @pytest.mark.asyncio
    async def test_client_called_with_word_and_meaning_in_prompt(self):
        client = make_client({"results": []})
        await self.checker.check(
            client, content="He runs fast.", word="run", meaning="跑", content_cn="他跑得很快。"
        )
        client.check.assert_called_once()
        _, user_prompt = client.check.call_args[0]
        assert "run" in user_prompt
        assert "跑" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_results_list_returns_empty(self):
        client = make_client({"results": []})
        results = await self.checker.check(
            client, content="She sings.", word="sing", meaning="唱歌"
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_ai_exception_returns_all_failed_results(self):
        client = make_failing_client(RuntimeError("network error"))
        results = await self.checker.check(
            client, content="She sings.", word="sing", meaning="唱歌"
        )
        assert len(results) == len(self.checker.rule_ids)
        assert all(r.passed is False for r in results)
        assert all("AI 调用失败" in r.detail for r in results)

    @pytest.mark.asyncio
    async def test_missing_meaning_uses_placeholder(self):
        client = make_client({"results": []})
        await self.checker.check(client, content="He runs.", word="run")
        _, user_prompt = client.check.call_args[0]
        assert "无" in user_prompt

    @pytest.mark.asyncio
    async def test_result_detail_none_when_not_provided(self):
        payload = {"results": [{"rule_id": "E1", "passed": True}]}
        client = make_client(payload)
        results = await self.checker.check(client, content="x", word="x")
        assert results[0].detail is None

    def test_dimension_attribute(self):
        assert self.checker.dimension == "sentence"

    def test_rule_ids_attribute(self):
        assert "E1" in self.checker.rule_ids
        assert "E9" in self.checker.rule_ids


# ---------------------------------------------------------------------------
# UnifiedChunkChecker
# ---------------------------------------------------------------------------


class TestUnifiedChunkChecker:
    checker = UnifiedChunkChecker()

    @pytest.mark.asyncio
    async def test_returns_c3_result_on_success(self):
        payload = {"results": [{"rule_id": "C3", "passed": True, "detail": "高频搭配"}]}
        client = make_client(payload)
        results = await self.checker.check(
            client, content="take care of", word="take", meaning="照顾"
        )
        assert len(results) == 1
        assert results[0].rule_id == "C3"
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_failed_chunk_propagated(self):
        payload = {"results": [{"rule_id": "C3", "passed": False, "detail": "非固定搭配"}]}
        client = make_client(payload)
        results = await self.checker.check(
            client, content="some random words", word="some", meaning="一些"
        )
        assert results[0].passed is False

    @pytest.mark.asyncio
    async def test_ai_exception_returns_failed_c3(self):
        client = make_failing_client(RuntimeError("timeout"))
        results = await self.checker.check(
            client, content="give up", word="give", meaning="放弃"
        )
        assert len(results) == 1
        assert results[0].rule_id == "C3"
        assert results[0].passed is False
        assert "AI 调用失败" in results[0].detail

    @pytest.mark.asyncio
    async def test_client_receives_word_and_content(self):
        client = make_client({"results": []})
        await self.checker.check(
            client, content="look after", word="look", meaning="照料"
        )
        client.check.assert_called_once()
        _, user_prompt = client.check.call_args[0]
        assert "look" in user_prompt
        assert "look after" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        client = make_client({"results": []})
        results = await self.checker.check(client, content="x", word="x")
        assert results == []

    def test_dimension_attribute(self):
        assert self.checker.dimension == "chunk"

    def test_rule_ids_contains_c3(self):
        assert "C3" in self.checker.rule_ids


# ---------------------------------------------------------------------------
# UnifiedMnemonicChecker
# ---------------------------------------------------------------------------


class TestUnifiedMnemonicChecker:
    checker = UnifiedMnemonicChecker()

    @pytest.mark.asyncio
    async def test_returns_n5_and_n6_results(self):
        payload = {
            "results": [
                {"rule_id": "N5_AI", "passed": True, "detail": "步骤完整"},
                {"rule_id": "N6", "passed": True, "detail": "逻辑合理"},
            ]
        }
        client = make_client(payload)
        results = await self.checker.check(
            client, content="拆分 ab+sent → 离开状态 → absent 缺席", word="absent"
        )
        assert len(results) == 2
        rule_ids = {r.rule_id for r in results}
        assert rule_ids == {"N5_AI", "N6"}

    @pytest.mark.asyncio
    async def test_n6_failed_pseudo_mnemonic(self):
        payload = {
            "results": [
                {"rule_id": "N5_AI", "passed": True, "detail": "ok"},
                {"rule_id": "N6", "passed": False, "detail": "伪助记，无实际帮助"},
            ]
        }
        client = make_client(payload)
        results = await self.checker.check(
            client, content="记住这个词：absent", word="absent"
        )
        n6 = next(r for r in results if r.rule_id == "N6")
        assert n6.passed is False
        assert "伪助记" in n6.detail

    @pytest.mark.asyncio
    async def test_ai_exception_returns_all_failed(self):
        client = make_failing_client(ValueError("parse error"))
        results = await self.checker.check(
            client, content="some mnemonic", word="test"
        )
        assert len(results) == len(self.checker.rule_ids)
        assert all(r.passed is False for r in results)
        assert all("AI 调用失败" in r.detail for r in results)

    @pytest.mark.asyncio
    async def test_client_receives_word_in_prompt(self):
        client = make_client({"results": []})
        await self.checker.check(client, content="助记内容", word="absent")
        _, user_prompt = client.check.call_args[0]
        assert "absent" in user_prompt

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_list(self):
        client = make_client({"results": []})
        results = await self.checker.check(client, content="x", word="x")
        assert results == []

    def test_dimension_attribute(self):
        assert self.checker.dimension == "mnemonic"

    def test_rule_ids_contains_n5_and_n6(self):
        assert "N5_AI" in self.checker.rule_ids
        assert "N6" in self.checker.rule_ids
