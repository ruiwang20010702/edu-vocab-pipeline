"""AI 用量追踪工具函数测试."""

import pytest

from vocab_qc.core.generators.base import AiUsageInfo, estimate_cost, extract_usage


class TestExtractUsage:
    """extract_usage 提取 AI 响应 usage 信息。"""

    def test_openai_format(self):
        """标准 OpenAI 响应格式。"""
        data = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        usage = extract_usage(data)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_gateway_format(self):
        """Gateway 包裹格式 {"res": {...}}。"""
        data = {
            "code": 10000,
            "res": {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
            },
        }
        usage = extract_usage(data)
        assert usage.prompt_tokens == 200
        assert usage.completion_tokens == 80
        assert usage.total_tokens == 280

    def test_missing_usage(self):
        """无 usage 字段返回零值。"""
        data = {"choices": [{"message": {"content": "{}"}}]}
        usage = extract_usage(data)
        assert usage == AiUsageInfo(0, 0, 0)

    def test_usage_none_values(self):
        """usage 中某些字段为 None 时安全处理。"""
        data = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": None, "completion_tokens": 30, "total_tokens": None},
        }
        usage = extract_usage(data)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 30
        assert usage.total_tokens == 0

    def test_usage_not_dict(self):
        """usage 不是 dict 时返回零值。"""
        data = {"choices": [{"message": {"content": "{}"}}], "usage": "invalid"}
        usage = extract_usage(data)
        assert usage == AiUsageInfo(0, 0, 0)

    def test_gateway_res_null(self):
        """Gateway 返回 res=null 不崩溃。"""
        data = {"code": 50000, "res": None}
        usage = extract_usage(data)
        assert usage == AiUsageInfo(0, 0, 0)

    def test_frozen_dataclass(self):
        """AiUsageInfo 是不可变的。"""
        usage = AiUsageInfo(10, 20, 30)
        with pytest.raises(AttributeError):
            usage.total_tokens = 99


class TestEstimateCost:
    """estimate_cost 费用估算。"""

    def test_known_model_gemini_flash(self):
        usage = AiUsageInfo(prompt_tokens=1_000_000, completion_tokens=500_000, total_tokens=1_500_000)
        cost = estimate_cost("gemini-2.0-flash", usage)
        # RMB: input: 1M * 0.00000365 = 3.65, output: 0.5M * 0.00002190 = 10.95, total = 14.60
        assert cost == 14.6

    def test_known_model_gpt(self):
        usage = AiUsageInfo(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = estimate_cost("gpt-5.2", usage)
        # RMB: input: 1000 * 0.00001278 = 0.01278, output: 500 * 0.00010220 = 0.05110, total = 0.06388
        assert cost == 0.06388

    def test_unknown_model(self):
        usage = AiUsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert estimate_cost("claude-3-opus", usage) is None

    def test_model_with_suffix(self):
        """带 |efficiency 后缀的模型名正确匹配。"""
        usage = AiUsageInfo(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        cost = estimate_cost("gpt-4o-mini|efficiency", usage)
        assert cost is not None

    def test_zero_tokens(self):
        usage = AiUsageInfo(0, 0, 0)
        cost = estimate_cost("gemini-2.0-flash", usage)
        assert cost == 0.0
