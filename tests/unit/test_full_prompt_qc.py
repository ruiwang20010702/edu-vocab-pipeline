"""完整 Prompt 质检测试。

验证：
1. build_ai_request use_json_format=False 不添加 response_format
2. AiClient.check use_json_format=False 返回 raw_text
3. parse_text_result 文本解析器
4. 全部 7 个维度的完整 prompt 分发、fallback、文本解析
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vocab_qc.core.generators.base import build_ai_request
from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.layer2.unified.full_prompt import (
    DIMENSION_FILE_MAP,
    load_full_prompt,
    parse_text_result,
)
from vocab_qc.core.qc.layer2.unified.mnemonic_unified import UnifiedMnemonicChecker
from vocab_qc.core.qc.layer2.unified.sentence_unified import UnifiedSentenceChecker
from vocab_qc.core.qc.layer2.unified.chunk_unified import UnifiedChunkChecker
from vocab_qc.core.qc.layer2.unified.syllable_unified import UnifiedSyllableChecker


# ---------------------------------------------------------------------------
# build_ai_request: use_json_format 参数
# ---------------------------------------------------------------------------


class TestBuildAiRequestJsonFormat:
    def test_json_format_true_includes_response_format(self):
        """use_json_format=True（默认）时包含 response_format。"""
        _, _, body = build_ai_request(
            "https://api.example.com", "key", "model",
            "system prompt with json", "user prompt",
        )
        assert "response_format" in body
        assert body["response_format"] == {"type": "json_object"}

    def test_json_format_false_excludes_response_format(self):
        """use_json_format=False 时不包含 response_format。"""
        _, _, body = build_ai_request(
            "https://api.example.com", "key", "model",
            "system prompt", "user prompt",
            use_json_format=False,
        )
        assert "response_format" not in body

    def test_json_format_false_no_json_hint_appended(self):
        """use_json_format=False 时不追加 JSON 提示。"""
        _, _, body = build_ai_request(
            "https://api.example.com", "key", "model",
            "You are a teacher.", "check this",
            use_json_format=False,
        )
        raw = body["messages"][0]["content"]
        system_text = raw[0]["text"] if isinstance(raw, list) else raw
        assert "json" not in system_text.lower()

    def test_json_format_true_appends_json_hint_if_missing(self):
        """use_json_format=True 时如果 prompt 中没有 json 关键词则追加。"""
        _, _, body = build_ai_request(
            "https://api.example.com", "key", "model",
            "You are a teacher.", "check this",
            use_json_format=True,
        )
        raw = body["messages"][0]["content"]
        system_text = raw[0]["text"] if isinstance(raw, list) else raw
        assert "json" in system_text.lower()

    @patch("vocab_qc.core.generators.base.settings")
    def test_gateway_mode_json_format_false(self, mock_settings):
        """Gateway 模式下 use_json_format=False 也不包含 response_format。"""
        mock_settings.ai_gateway_mode = True
        mock_settings.ai_gateway_async = False
        mock_settings.ai_gateway_biz_type = "test"
        mock_settings.ai_gateway_provider = "VERTEX"
        _, _, body = build_ai_request(
            "https://gw.example.com", "key", "gemini-2.5-flash",
            "system prompt", "user prompt",
            use_json_format=False,
        )
        assert "response_format" not in body


# ---------------------------------------------------------------------------
# parse_text_result: 文本解析器
# ---------------------------------------------------------------------------


class TestParseTextResult:
    rule_ids = ["N5_AI", "N6"]

    def test_all_pass(self):
        text = """Etymology Validity: PASS
Formula Accuracy: PASS
Chant–Formula Coherence: PASS
Script 6-Step Framework: PASS
Scene Logic: PASS
Word Family Accuracy: PASS
Prop Ban: PASS
Tone & Style: PASS
Content Safety: PASS
OVERALL: PASS"""
        results = parse_text_result(text, self.rule_ids)
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_single_fail(self):
        text = """Etymology Validity: PASS
Formula Accuracy: FAIL — 后缀标注不匹配词性
Chant–Formula Coherence: PASS
OVERALL: FAIL"""
        results = parse_text_result(text, self.rule_ids)
        assert any(not r.passed for r in results)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1
        assert "Formula Accuracy" in failed[0].detail

    def test_multiple_fails(self):
        text = """Etymology Validity: FAIL — 伪词源
Formula Accuracy: FAIL — 中文含义错误
Script 6-Step Framework: PASS
OVERALL: FAIL"""
        results = parse_text_result(text, self.rule_ids)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1  # 所有 fail 合并到第一个 rule_id
        assert "Etymology Validity" in failed[0].detail
        assert "Formula Accuracy" in failed[0].detail

    def test_chinese_status(self):
        """支持中文 通过/不通过。"""
        text = """词源准确性: 通过
公式准确性: 不通过 — 后缀标注错误
OVERALL: FAIL"""
        results = parse_text_result(text, self.rule_ids)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1

    def test_empty_text(self):
        results = parse_text_result("", self.rule_ids)
        assert all(r.passed for r in results)

    def test_only_overall_fail(self):
        text = "OVERALL: FAIL"
        results = parse_text_result(text, self.rule_ids)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_client(return_value: dict) -> MagicMock:
    client = MagicMock()
    client.check = AsyncMock(return_value=return_value)
    return client


# ---------------------------------------------------------------------------
# UnifiedMnemonicChecker: 维度分发逻辑
# ---------------------------------------------------------------------------


class TestMnemonicCheckerDispatch:
    checker = UnifiedMnemonicChecker()

    @pytest.mark.asyncio
    async def test_root_affix_uses_full_prompt(self):
        """mnemonic_root_affix 维度使用完整 prompt（use_json_format=False）。"""
        all_pass_text = "Etymology Validity: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="in(不)+vis(看)+ible(形容词后缀)", word="invisible",
            meaning="看不见的", item_dimension="mnemonic_root_affix",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False
        assert len(results) == 2
        assert all(isinstance(r, RuleResult) for r in results)

    @pytest.mark.asyncio
    async def test_word_in_word_uses_full_prompt(self):
        """mnemonic_word_in_word 维度也使用完整 prompt。"""
        all_pass_text = "检查项1: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="dog 里有 do", word="dog",
            meaning="狗", item_dimension="mnemonic_word_in_word",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_sound_meaning_uses_full_prompt(self):
        """mnemonic_sound_meaning 维度使用完整 prompt。"""
        all_pass_text = "检查项1: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="content", word="test",
            meaning="测试", item_dimension="mnemonic_sound_meaning",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False

    @pytest.mark.asyncio
    async def test_exam_app_uses_full_prompt(self):
        """mnemonic_exam_app 维度使用完整 prompt。"""
        all_pass_text = "检查项1: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="content", word="test",
            meaning="测试", item_dimension="mnemonic_exam_app",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False

    @pytest.mark.asyncio
    async def test_no_dimension_uses_simple_prompt(self):
        """未传 item_dimension 时使用精简 prompt。"""
        payload = {"results": [{"rule_id": "N5_AI", "passed": True}]}
        client = _make_client(payload)

        results = await self.checker.check(
            client, content="some content", word="test",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format", True) is True

    @pytest.mark.asyncio
    async def test_fallback_on_missing_prompt_file(self):
        """完整 prompt 文件不存在时回退到精简模式。"""
        payload = {
            "results": [
                {"rule_id": "N5_AI", "passed": True, "detail": "ok"},
                {"rule_id": "N6", "passed": True, "detail": "ok"},
            ]
        }
        client = _make_client(payload)

        with patch(
            "vocab_qc.core.qc.layer2.unified.mnemonic_unified.load_full_prompt",
            return_value=None,
        ):
            results = await self.checker.check(
                client, content="content", word="test",
                meaning="测试", item_dimension="mnemonic_root_affix",
            )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_ai_failure_returns_all_failed(self):
        """完整 prompt 模式 AI 调用失败时返回全部 FAIL。"""
        client = MagicMock()
        client.check = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await self.checker.check(
            client, content="content", word="test",
            meaning="测试", item_dimension="mnemonic_root_affix",
        )

        assert len(results) == 2
        assert all(not r.passed for r in results)
        assert all("AI 调用失败" in r.detail for r in results)


# ---------------------------------------------------------------------------
# UnifiedSentenceChecker: 完整 prompt 分发
# ---------------------------------------------------------------------------


class TestSentenceCheckerFullPrompt:
    checker = UnifiedSentenceChecker()

    @pytest.mark.asyncio
    async def test_uses_full_prompt(self):
        """例句维度使用完整 prompt。"""
        all_pass_text = "语法: PASS\n翻译: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="She goes to school.", word="go",
            meaning="去", content_cn="她去上学。",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False
        assert len(results) == len(self.checker.rule_ids)
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_fallback_to_simple(self):
        """完整 prompt 不存在时回退 JSON 模式。"""
        payload = {"results": [{"rule_id": "E1", "passed": True, "detail": "ok"}]}
        client = _make_client(payload)

        with patch(
            "vocab_qc.core.qc.layer2.unified.sentence_unified.load_full_prompt",
            return_value=None,
        ):
            results = await self.checker.check(
                client, content="test", word="test",
            )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format", True) is True

    @pytest.mark.asyncio
    async def test_ai_failure(self):
        """AI 调用失败时返回全部 FAIL。"""
        client = MagicMock()
        client.check = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await self.checker.check(
            client, content="test", word="test",
        )

        assert len(results) == len(self.checker.rule_ids)
        assert all(not r.passed for r in results)


# ---------------------------------------------------------------------------
# UnifiedChunkChecker: 完整 prompt 分发
# ---------------------------------------------------------------------------


class TestChunkCheckerFullPrompt:
    checker = UnifiedChunkChecker()

    @pytest.mark.asyncio
    async def test_uses_full_prompt(self):
        """语块维度使用完整 prompt。"""
        all_pass_text = "搭配: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="go to school", word="go", meaning="去",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False
        assert len(results) == 1
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_fallback_to_simple(self):
        """完整 prompt 不存在时回退 JSON 模式。"""
        payload = {"results": [{"rule_id": "C3", "passed": True, "detail": "ok"}]}
        client = _make_client(payload)

        with patch(
            "vocab_qc.core.qc.layer2.unified.chunk_unified.load_full_prompt",
            return_value=None,
        ):
            results = await self.checker.check(
                client, content="test", word="test",
            )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format", True) is True

    @pytest.mark.asyncio
    async def test_ai_failure(self):
        """AI 调用失败时返回全部 FAIL。"""
        client = MagicMock()
        client.check = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await self.checker.check(
            client, content="test", word="test",
        )

        assert len(results) == 1
        assert not results[0].passed


# ---------------------------------------------------------------------------
# UnifiedSyllableChecker: 完整 prompt 分发
# ---------------------------------------------------------------------------


class TestSyllableCheckerFullPrompt:
    checker = UnifiedSyllableChecker()

    @pytest.mark.asyncio
    async def test_uses_full_prompt(self):
        """音节维度使用完整 prompt。"""
        all_pass_text = "单音节: PASS\n元音锚点: PASS\nOVERALL: PASS"
        client = _make_client({"raw_text": all_pass_text})

        results = await self.checker.check(
            client, content="ap·ple", word="apple",
        )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format") is False
        assert len(results) == len(self.checker.rule_ids)
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_fallback_to_simple(self):
        """完整 prompt 不存在时回退 JSON 模式。"""
        payload = {"results": [{"rule_id": "SA1", "passed": True, "detail": "ok"}]}
        client = _make_client(payload)

        with patch(
            "vocab_qc.core.qc.layer2.unified.syllable_unified.load_full_prompt",
            return_value=None,
        ):
            results = await self.checker.check(
                client, content="test", word="test",
            )

        call_kwargs = client.check.call_args
        assert call_kwargs.kwargs.get("use_json_format", True) is True

    @pytest.mark.asyncio
    async def test_ai_failure(self):
        """AI 调用失败时返回全部 FAIL。"""
        client = MagicMock()
        client.check = AsyncMock(side_effect=RuntimeError("timeout"))

        results = await self.checker.check(
            client, content="test", word="test",
        )

        assert len(results) == len(self.checker.rule_ids)
        assert all(not r.passed for r in results)


# ---------------------------------------------------------------------------
# load_full_prompt: 全部 7 个维度加载验证
# ---------------------------------------------------------------------------


class TestLoadFullPrompt:
    @pytest.mark.parametrize("dimension", list(DIMENSION_FILE_MAP.keys()))
    def test_loads_all_dimensions(self, dimension):
        """验证所有 7 个维度的完整 prompt 文件都能加载。"""
        # 清除缓存以确保实际读取文件
        from vocab_qc.core.qc.layer2.unified import full_prompt
        full_prompt._full_prompt_cache.pop(dimension, None)

        prompt = load_full_prompt(dimension)
        assert prompt is not None, f"{dimension} 对应的 prompt 文件不存在"
        assert len(prompt) > 100, f"{dimension} prompt 内容过短"

    def test_unknown_dimension_returns_none(self):
        assert load_full_prompt("nonexistent") is None
