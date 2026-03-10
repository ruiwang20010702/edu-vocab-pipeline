"""Mnemonic 维度 Layer 1 规则: N1, N2, N3, N4, N5."""

import json
from typing import Any, Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase


def _parse_mnemonic_json(content: str) -> dict[str, Any] | None:
    """解析助记 JSON content，返回 dict 或 None."""
    if not content:
        return None
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


@RuleRegistry.register_layer1
class N1MnemonicType(_RuleCheckerBase):
    """N1: 助记内容必须为合法 JSON，包含 formula/chant/script 键."""

    rule_id = "N1"
    dimension = "mnemonic"
    description = "助记格式校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        required_keys = {"formula", "chant", "script"}
        missing = required_keys - set(data.keys())
        if missing:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"JSON 缺少必要字段: {', '.join(sorted(missing))}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


@RuleRegistry.register_layer1
class N2StructureCompleteness(_RuleCheckerBase):
    """N2: 每个字段（formula/chant/script）非空."""

    rule_id = "N2"
    dimension = "mnemonic"
    description = "助记结构完整性校验"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        empty_fields = [k for k in ("formula", "chant", "script") if not str(data.get(k, "")).strip()]
        if empty_fields:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"以下字段为空: {', '.join(empty_fields)}",
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

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        formula = str(data.get("formula", "")).strip()
        if not formula:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到核心公式部分")

        if "+" not in formula and "≈" not in formula and "=" not in formula:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
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

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        chant = str(data.get("chant", "")).strip().strip('"')
        if not chant:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到口诀部分")

        # 通过 dimension kwarg 判断是否为考试应用类
        dimension = kwargs.get("dimension", "")
        is_exam = dimension == "mnemonic_exam_app"
        max_chars = 30 if is_exam else 15

        char_count = len(chant)
        if char_count > max_chars:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"口诀字数({char_count})超过上限({max_chars}): {chant!r}",
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

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        script = str(data.get("script", "")).strip()
        if not script:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="未找到老师话术部分")

        char_count = len(script)

        target = 500
        tolerance = 0.2
        lower = int(target * (1 - tolerance))  # 400
        upper = int(target * (1 + tolerance))  # 600

        if char_count < lower:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"话术字数({char_count})低于下限({lower})",
            )
        if char_count > upper:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"话术字数({char_count})超过上限({upper})",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)
