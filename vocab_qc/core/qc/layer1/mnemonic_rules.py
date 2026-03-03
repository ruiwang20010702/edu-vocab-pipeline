"""Mnemonic 维度 Layer 1 规则: N1, N2, N3, N4, N5."""

import re
from typing import Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase

VALID_MNEMONIC_TYPES = {"词根词缀", "词中词", "音义联想", "考试应用"}

# 助记结构的 4 部分及其匹配模式
# [助记类型] 实际使用时写为具体类型名，如 [词中词]、[词根词缀] 等
_TYPE_NAMES = "|".join(re.escape(t) for t in VALID_MNEMONIC_TYPES)
STRUCTURE_MARKERS = ["[助记类型]", "[核心公式]", "[助记口诀]", "[老师话术]"]
STRUCTURE_PATTERNS = [
    rf"\[(?:助记类型|{_TYPE_NAMES})\]",  # 匹配 [助记类型] 或具体类型如 [词中词]
    r"\[核心公式\]",
    r"\[助记口诀[/\w]*\]",  # 匹配 [助记口诀] 或 [助记口诀/逻辑]
    r"\[老师话术\]",
]


@RuleRegistry.register_layer1
class N1MnemonicType(_RuleCheckerBase):
    """N1: 助记类型必须从 4 类中选择."""

    rule_id = "N1"
    dimension = "mnemonic"
    description = "助记类型校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        # 从内容中提取类型标记
        type_match = re.search(r"\[(\w+)\]", content)
        if not type_match:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到助记类型标记")

        mnemonic_type = type_match.group(1)
        if mnemonic_type not in VALID_MNEMONIC_TYPES:
            # 也检查第一行是否直接写了类型
            first_line = content.strip().split("\n")[0].strip().strip("[]")
            if first_line not in VALID_MNEMONIC_TYPES:
                return RuleResult(
                    rule_id=self.rule_id,
                    passed=False,
                    detail=f"非法助记类型: {mnemonic_type!r}",
                )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class N2StructureCompleteness(_RuleCheckerBase):
    """N2: 每组助记包含完整 4 部分结构."""

    rule_id = "N2"
    dimension = "mnemonic"
    description = "助记结构完整性校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        missing = []
        for i, pattern in enumerate(STRUCTURE_PATTERNS):
            if not re.search(pattern, content):
                missing.append(STRUCTURE_MARKERS[i])

        if missing:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"缺少结构部分: {', '.join(missing)}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class N3FormulaSymbol(_RuleCheckerBase):
    """N3: 核心公式使用 + 或 ≈ 进行逻辑拆解."""

    rule_id = "N3"
    dimension = "mnemonic"
    description = "公式符号校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        # 提取核心公式部分
        formula_match = re.search(r"\[核心公式\]\s*(.+?)(?:\n|\[|$)", content, re.DOTALL)
        if not formula_match:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到核心公式部分")

        formula = formula_match.group(1).strip()
        if "+" not in formula and "≈" not in formula and "=" not in formula:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"公式未使用 +/≈/= 符号: {formula!r}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class N4FormulaLength(_RuleCheckerBase):
    """N4: 口诀/逻辑字数 ≤ 15 字（考试应用类 ≤ 30 字）."""

    rule_id = "N4"
    dimension = "mnemonic"
    description = "口诀字数校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        # 提取口诀部分
        slogan_match = re.search(r"\[助记口诀[/\w]*\]\s*(.+?)(?:\n\[|$)", content, re.DOTALL)
        if not slogan_match:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到口诀部分")

        slogan = slogan_match.group(1).strip().strip('"')

        # 判断是否为考试应用类
        is_exam = "考试应用" in content
        max_chars = 30 if is_exam else 15

        # 统计中文字符 + 英文单词的字数
        char_count = len(slogan)
        if char_count > max_chars:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"口诀字数({char_count})超过上限({max_chars}): {slogan!r}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class N5TeacherScriptLength(_RuleCheckerBase):
    """N5: 老师话术约 500 字（±20% 浮动）."""

    rule_id = "N5"
    dimension = "mnemonic"
    description = "话术字数校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        # 提取老师话术部分
        script_match = re.search(r"\[老师话术\]\s*(.+)", content, re.DOTALL)
        if not script_match:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到老师话术部分")

        script = script_match.group(1).strip()
        char_count = len(script)

        target = 500
        tolerance = 0.2
        lower = int(target * (1 - tolerance))  # 400
        upper = int(target * (1 + tolerance))  # 600

        if char_count < lower:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"话术字数({char_count})低于下限({lower})",
            )
        if char_count > upper:
            return RuleResult(
                rule_id=self.rule_id,
                passed=False,
                detail=f"话术字数({char_count})超过上限({upper})",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)
