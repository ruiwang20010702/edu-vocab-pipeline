"""Chunk 维度 Layer 1 规则: C1, C2, C4, C5."""

import re
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase


@RuleRegistry.register_layer1
class C1ChunkContainsWord(_RuleCheckerBase):
    """C1: 语块包含目标词."""

    rule_id = "C1"
    dimension = "chunk"
    description = "语块含目标词校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content or not word:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少语块或目标词")

        # 忽略大小写匹配，支持常见变形（复数、过去式等）
        word_lower = word.lower()
        content_lower = content.lower()

        # 直接包含
        if word_lower in content_lower:
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 常见变形：+s, +es, +ed, +ing, +er, +est, +ly
        stems = [
            word_lower + "s",
            word_lower + "es",
            word_lower + "ed",
            word_lower + "ing",
            word_lower + "er",
            word_lower + "est",
            word_lower + "ly",
        ]
        # 去 e 加 ing/ed: make → making
        if word_lower.endswith("e"):
            stems.append(word_lower[:-1] + "ing")
            stems.append(word_lower[:-1] + "ed")
        # 双写末字母：run → running
        if len(word_lower) >= 3 and word_lower[-1] not in "aeiouy" and word_lower[-2] in "aeiouy":
            stems.append(word_lower + word_lower[-1] + "ing")
            stems.append(word_lower + word_lower[-1] + "ed")
        # y 结尾变形：happy → happier, happiness
        if word_lower.endswith("y"):
            stems.append(word_lower[:-1] + "ies")
            stems.append(word_lower[:-1] + "ied")
            stems.append(word_lower[:-1] + "ier")
            stems.append(word_lower[:-1] + "iest")
            stems.append(word_lower[:-1] + "ily")

        for stem in stems:
            if stem in content_lower:
                return RuleResult(rule_id=self.rule_id, passed=True)

        return RuleResult(rule_id=self.rule_id, passed=False, detail=f"语块不包含目标词 '{word}'")


@RuleRegistry.register_layer1
class C2ChunkLength(_RuleCheckerBase):
    """C2: 语块长度 2–5 词."""

    rule_id = "C2"
    dimension = "chunk"
    description = "语块长度校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少语块内容")

        # 只取英文部分（第一行或斜杠前）
        english_part = content.split("\n")[0].strip()
        word_count = len(english_part.split())

        if word_count < 2:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"语块过短: {word_count}词")
        if word_count > 5:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"语块过长: {word_count}词")

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class C4NoBrackets(_RuleCheckerBase):
    """C4: 语块禁止使用括号."""

    rule_id = "C4"
    dimension = "chunk"
    description = "语块禁止括号校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if "(" in content or ")" in content or "（" in content or "）" in content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="语块包含括号")
        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class C5ChineseOnSeparateLine(_RuleCheckerBase):
    """C5: 中文对照独立成行，不得包裹在英文后的括号内."""

    rule_id = "C5"
    dimension = "chunk"
    description = "中文独立成行校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        content_cn = kwargs.get("content_cn", "")

        # 如果没有中文翻译字段，检查语块本身是否混杂了中文
        if not content_cn:
            # 检查内容中是否包含中文字符（除了 sb./sth. 这类占位符）
            has_chinese = bool(re.search(r"[\u4e00-\u9fff]", content))
            if has_chinese:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail="中文内容混在英文语块中，应独立成行",
                )
        return RuleResult(rule_id=self.rule_id, passed=True)
