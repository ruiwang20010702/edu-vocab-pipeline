"""Sentence 维度 Layer 1 规则: E6, E7, E8."""

import re
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase


@RuleRegistry.register_layer1
class E6SentenceContainsWord(_RuleCheckerBase):
    """E6: 例句必须包含目标词（或其常见变形）."""

    rule_id = "E6"
    dimension = "sentence"
    description = "例句含目标词校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content or not word:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少例句或目标词")

        word_lower = word.lower()
        content_lower = content.lower()

        if word_lower in content_lower:
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 常见变形
        stems = [
            word_lower + "s",
            word_lower + "es",
            word_lower + "ed",
            word_lower + "ing",
            word_lower + "er",
            word_lower + "est",
            word_lower + "ly",
        ]
        if word_lower.endswith("e"):
            stems.extend([word_lower[:-1] + "ing", word_lower[:-1] + "ed"])
        if len(word_lower) >= 3 and word_lower[-1] not in "aeiouy" and word_lower[-2] in "aeiouy":
            stems.extend([word_lower + word_lower[-1] + "ing", word_lower + word_lower[-1] + "ed"])
        if word_lower.endswith("y"):
            stems.extend([
                word_lower[:-1] + "ies",
                word_lower[:-1] + "ied",
                word_lower[:-1] + "ier",
                word_lower[:-1] + "iest",
                word_lower[:-1] + "ily",
            ])

        for stem in stems:
            if stem in content_lower:
                return RuleResult(rule_id=self.rule_id, passed=True)

        return RuleResult(rule_id=self.rule_id, passed=False, detail=f"例句不包含目标词 '{word}' 或其变形")


@RuleRegistry.register_layer1
class E7SentenceLength(_RuleCheckerBase):
    """E7: 例句长度 5–20 词."""

    rule_id = "E7"
    dimension = "sentence"
    description = "例句长度校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少例句")

        # 只取英文部分
        english_part = content.split("\n")[0].strip()
        word_count = len(english_part.split())

        if word_count < 5:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"例句过短: {word_count}词")
        if word_count > 20:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"例句过长: {word_count}词")

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class E8HasChineseTranslation(_RuleCheckerBase):
    """E8: 例句必须配有中文翻译（非空校验部分）."""

    rule_id = "E8"
    dimension = "sentence"
    description = "中文翻译非空校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        content_cn = kwargs.get("content_cn", "")

        if not content_cn or not content_cn.strip():
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少中文翻译")

        # 检查是否包含至少一个中文字符
        if not re.search(r"[\u4e00-\u9fff]", content_cn):
            return RuleResult(rule_id=self.rule_id, passed=False, detail="翻译不包含中文字符")

        return RuleResult(rule_id=self.rule_id, passed=True)
