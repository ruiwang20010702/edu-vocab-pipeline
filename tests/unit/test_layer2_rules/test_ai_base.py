"""Layer 2 AI 基础设施测试."""

import asyncio

from vocab_qc.core.qc.layer2.ai_base import AiClient
from vocab_qc.core.qc.registry import RuleRegistry


def test_layer2_rules_registered():
    """验证 Layer 2 规则已注册."""
    import vocab_qc.core.qc.layer2.per_rule  # noqa: F401

    rules = RuleRegistry.get_layer2_rules()
    assert len(rules) >= 13
    # 检查关键规则
    rule_ids = set(rules.keys())
    assert "M7" in rule_ids
    assert "C3" in rule_ids
    assert "E1" in rule_ids
    assert "E9" in rule_ids
    assert "N6" in rule_ids


def test_ai_client_placeholder_mode():
    """测试无 API 配置时的占位模式."""
    client = AiClient(api_key="", base_url="")
    result = asyncio.run(client.check("system", "user"))
    assert result["passed"] is True
    assert "占位模式" in result["detail"]


def test_ai_rule_checker_placeholder():
    """测试 AI 规则检查器的占位模式."""
    import vocab_qc.core.qc.layer2.per_rule  # noqa: F401

    rules = RuleRegistry.get_layer2_rules()
    client = AiClient(api_key="", base_url="")

    # 选一个检查器测试
    checker = rules["C3"]
    result = asyncio.run(checker.check(client, "be kind to sb.", "kind", "友好的"))
    assert result.rule_id == "C3"
    assert result.passed is True  # 占位模式默认通过


def test_layer2_rules_by_dimension():
    """按维度筛选 Layer 2 规则."""
    import vocab_qc.core.qc.layer2.per_rule  # noqa: F401

    sentence_rules = RuleRegistry.get_layer2_rules(dimension="sentence")
    assert len(sentence_rules) >= 9  # E1-E5, E8_AI, E9, E10, E11

    mnemonic_rules = RuleRegistry.get_layer2_rules(dimension="mnemonic")
    assert len(mnemonic_rules) >= 2  # N5_AI, N6
