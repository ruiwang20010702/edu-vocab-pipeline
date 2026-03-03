"""Meaning 维度 Layer 1 规则: M3, M4, M5, M6."""

import re
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase

VALID_POS_TAGS = {"n.", "v.", "adj.", "adv.", "prep.", "conj.", "pron.", "num.", "art.", "int."}


@RuleRegistry.register_layer1
class M3PosTagFormat(_RuleCheckerBase):
    """M3: 词性标签使用统一缩写."""

    rule_id = "M3"
    dimension = "meaning"
    description = "词性标签格式校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        pos = kwargs.get("pos", "")
        if not pos:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少词性标签")
        if pos not in VALID_POS_TAGS:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"非法词性标签: {pos!r}")
        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class M4PosNewlineSeparation(_RuleCheckerBase):
    """M4: 不同词性之间换行分隔."""

    rule_id = "M4"
    dimension = "meaning"
    description = "词性换行分隔校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content or not content.strip():
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 用正则找出所有词性标签出现的位置
        pos_escaped = "|".join(re.escape(p) for p in VALID_POS_TAGS)
        pos_re = re.compile(r"(?:^|\s)(" + pos_escaped + r")")

        lines = [line.strip() for line in content.strip().split("\n") if line.strip()]

        for line in lines:
            matches = pos_re.findall(line)
            if len(matches) > 1:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"同一行包含多个词性标签: {line!r}",
                )
        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class M5SemicolonSeparation(_RuleCheckerBase):
    """M5: 同词性下不同义项使用分号分隔."""

    rule_id = "M5"
    dimension = "meaning"
    description = "义项分号分隔校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        # 检查同一行中如果有多个释义，是否用分号分隔
        # 策略：如果一行有多个中文短语，它们之间应该用分号分隔
        definition = meaning or content
        if not definition:
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 检查是否用逗号而非分号分隔了多个义项
        # 典型错误："友好的，善良的" → 应为 "友好的；善良的"
        if "，" in definition and "；" not in definition:
            # 可能有多个义项用逗号分隔
            parts = definition.split("，")
            if len(parts) >= 2:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"疑似多义项用逗号而非分号分隔: {definition!r}",
                )
        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class M6NoBrackets(_RuleCheckerBase):
    """M6: 禁止使用括号做解释说明."""

    rule_id = "M6"
    dimension = "meaning"
    description = "禁止括号校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        text = meaning or content
        if "(" in text or ")" in text or "（" in text or "）" in text:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"释义中包含括号: {text!r}")
        return RuleResult(rule_id=self.rule_id, passed=True)
