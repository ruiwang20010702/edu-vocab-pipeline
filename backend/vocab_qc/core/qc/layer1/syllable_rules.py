"""Syllable 维度 Layer 1 规则: S1, S2, S3, S4."""

import re
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase

# 原子单位列表（不可从中拆分）
CONSONANT_DIGRAPHS = {"ch", "ck", "gh", "gn", "kn", "ng", "ph", "qu", "sc", "sh", "th", "wh", "wr"}
VOWEL_DIGRAPHS = {"ai", "ay", "ea", "ee", "ey", "ie", "oa", "oe", "oo", "ou", "ow", "ue", "ui"}
R_VOWELS = {"ar", "er", "ir", "or", "ur"}
ALL_ATOMIC_UNITS = CONSONANT_DIGRAPHS | VOWEL_DIGRAPHS | R_VOWELS

# 英语元音字母
VOWELS = set("aeiouyAEIOUY")


@RuleRegistry.register_layer1
class S1VowelAnchor(_RuleCheckerBase):
    """S1: 每个切分块包含且仅包含一个实际发声的元音（-le 除外）."""

    rule_id = "S1"
    dimension = "syllable"
    description = "元音锚点校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        # 校验 ContentItem 自身的 content（生产产出），而非 Phonetic 表的 syllables
        syllables_str = content
        if not syllables_str:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音节数据")

        parts = syllables_str.split("·")
        for part in parts:
            part_lower = part.strip().lower()
            if not part_lower:
                continue

            # -le 例外：词尾成节音
            if part_lower.endswith("le") and len(part_lower) >= 3:
                # 如 "ble", "tle", "ple" — 允许无传统元音
                consonant_before = part_lower[:-2]
                vowel_count = sum(1 for c in consonant_before if c in "aeiouy")
                if vowel_count == 0:
                    continue

            # 计算元音字母数（粗略检查）
            # 注意：元音二合字母(ee, ea等)算一个元音
            vowel_groups = re.findall(r"[aeiouy]+", part_lower)
            if len(vowel_groups) == 0:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"切分块 '{part}' 不包含元音",
                )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class S2Separator(_RuleCheckerBase):
    """S2: 统一使用中圆点 · 作为分隔符."""

    rule_id = "S2"
    dimension = "syllable"
    description = "音节分隔符校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        syllables_str = content
        if not syllables_str:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音节数据")

        # 正确的分隔符: 中圆点 U+00B7 (·)
        correct_sep = "\u00b7"

        # 如果只有一个音节（无任何分隔符），通过
        wrong_separators = ["-", ".", "\u2027", "\u2022", "\u2024", "|"]
        has_correct = correct_sep in syllables_str
        has_wrong = any(sep in syllables_str for sep in wrong_separators)

        if not has_correct and not has_wrong:
            # 单音节词，无分隔符
            return RuleResult(rule_id=self.rule_id, passed=True)

        if has_wrong:
            found = [sep for sep in wrong_separators if sep in syllables_str]
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"使用了错误的分隔符 {found!r}，应使用 '·' (U+00B7)",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class S3AtomicUnitIntegrity(_RuleCheckerBase):
    """S3: 原子单位禁止从中拆分（如 sh, ee, ph, ar）."""

    rule_id = "S3"
    dimension = "syllable"
    description = "原子单位完整性校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        syllables_str = content
        if not syllables_str:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音节数据")

        parts = syllables_str.split("·")
        if len(parts) <= 1:
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 检查相邻切分块的边界是否拆分了原子单位
        for i in range(len(parts) - 1):
            current_end = parts[i].strip().lower()
            next_start = parts[i + 1].strip().lower()
            if not current_end or not next_start:
                continue

            # 检查跨越边界的二合字母
            boundary = current_end[-1] + next_start[0]
            if boundary in ALL_ATOMIC_UNITS:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"原子单位 '{boundary}' 被拆分在 '{parts[i]}·{parts[i+1]}' 边界",
                )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class S4SingleSyllableNoSplit(_RuleCheckerBase):
    """S4: 单音节词不做切分."""

    rule_id = "S4"
    dimension = "syllable"
    description = "单音节不切分校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        syllables_str = content
        if not syllables_str:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少音节数据")

        # 判断是否为单音节词（ipa 来自 Phonetic 表，用于交叉验证）
        ipa = kwargs.get("ipa", "")
        parts = syllables_str.split("·")

        # 如果只有一个切分块，通过
        if len(parts) == 1:
            return RuleResult(rule_id=self.rule_id, passed=True)

        # 如果音标中没有分隔符（单音节），但切分块有多个，则失败
        if ipa:
            ipa_inner = ipa.strip("/")
            if "·" not in ipa_inner and len(parts) > 1:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"单音节词被错误切分: {syllables_str!r}",
                )

        return RuleResult(rule_id=self.rule_id, passed=True)
