"""规则注册中心：装饰器自动注册."""

from typing import Optional

from vocab_qc.core.qc.base import RuleChecker, RuleResult

# 助记规则维度匹配: dimension="mnemonic" 的规则适用于所有 mnemonic_* 维度
_MNEMONIC_RULE_DIM = "mnemonic"


def _dimension_matches(rule_dim: str, query_dim: str) -> bool:
    """判断规则维度是否匹配查询维度."""
    if rule_dim == query_dim:
        return True
    if rule_dim == _MNEMONIC_RULE_DIM and query_dim.startswith("mnemonic_"):
        return True
    return False


class _RuleCheckerBase:
    """Layer 1 规则检查器基类（具体实现继承此类）."""

    rule_id: str = ""
    dimension: str = ""
    description: str = ""

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        raise NotImplementedError


class RuleRegistry:
    """规则注册中心."""

    _layer1_rules: dict[str, _RuleCheckerBase] = {}
    _layer2_rules: dict[str, object] = {}

    @classmethod
    def register_layer1(cls, checker_cls: type[_RuleCheckerBase]) -> type[_RuleCheckerBase]:
        instance = checker_cls()
        cls._layer1_rules[instance.rule_id] = instance
        return checker_cls

    @classmethod
    def register_layer2(cls, checker_cls: type) -> type:
        instance = checker_cls()
        cls._layer2_rules[instance.rule_id] = instance
        return checker_cls

    @classmethod
    def get_layer1_rules(cls, dimension: Optional[str] = None) -> dict[str, _RuleCheckerBase]:
        if dimension is None:
            return dict(cls._layer1_rules)
        return {k: v for k, v in cls._layer1_rules.items() if _dimension_matches(v.dimension, dimension)}

    @classmethod
    def get_layer2_rules(cls, dimension: Optional[str] = None) -> dict[str, object]:
        if dimension is None:
            return dict(cls._layer2_rules)
        return {k: v for k, v in cls._layer2_rules.items() if _dimension_matches(v.dimension, dimension)}

    @classmethod
    def get_layer1_rule(cls, rule_id: str) -> Optional[_RuleCheckerBase]:
        return cls._layer1_rules.get(rule_id)

    @classmethod
    def clear(cls):
        """仅用于测试."""
        cls._layer1_rules.clear()
        cls._layer2_rules.clear()
