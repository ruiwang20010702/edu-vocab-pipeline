"""规则检查器基类."""

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class RuleResult:
    """单条规则的检查结果."""

    rule_id: str
    passed: bool
    detail: Optional[str] = None


@dataclass(frozen=True)
class ItemCheckResult:
    """一个内容项的全部规则检查结果."""

    content_item_id: int
    word_id: int
    meaning_id: Optional[int]
    dimension: str
    results: list[RuleResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failed_rules(self) -> list[RuleResult]:
        return [r for r in self.results if not r.passed]


class RuleChecker(Protocol):
    """Layer 1 规则检查器协议."""

    rule_id: str
    dimension: str
    description: str

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult: ...
