"""Mnemonic 维度 Layer 1 规则: N1, N2, N3, N4, N5."""

import json
import re
from typing import Any, Optional

from vocab_qc.core.qc.base import RuleResult
from vocab_qc.core.qc.registry import RuleRegistry, _RuleCheckerBase


def count_logical_chars(text: str) -> int:
    """中英混排逻辑字数统计：连续英文字母算 1 个字，中文字符算 1 个字，标点符号不计."""
    # 连续英文字母替换为单个占位符
    collapsed = re.sub(r"[a-zA-Z]+", "¤", text)
    # 只计中文字符和占位符（英文词），忽略标点、空格、数字等
    return sum(1 for ch in collapsed if ch == "¤" or "\u4e00" <= ch <= "\u9fff")


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

        char_count = count_logical_chars(chant)
        if char_count > max_chars:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"口诀字数({char_count})超过上限({max_chars}): {chant!r}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


# 话术字数边界：(下限, 上限)；上限为 None 表示无上限.
_SCRIPT_LENGTH_BOUNDS: dict[str, tuple[int, Optional[int]]] = {
    "mnemonic_sound_meaning": (400, None),
    # 1v1 私教风格新版：200-250 字
    "mnemonic_exam_app": (200, 250),
}
_DEFAULT_SCRIPT_LOWER = 500


@RuleRegistry.register_layer1
class N5TeacherScriptLength(_RuleCheckerBase):
    """N5: 老师话术字数校验（音义联想 ≥400，考试应用 200-250，词中词/词根词缀 ≥500）."""

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

        char_count = count_logical_chars(script)

        dimension = kwargs.get("dimension", "")
        lower, upper = _SCRIPT_LENGTH_BOUNDS.get(dimension, (_DEFAULT_SCRIPT_LOWER, None))

        if char_count < lower:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"话术字数({char_count})低于下限({lower})",
            )
        if upper is not None and char_count > upper:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"话术字数({char_count})超过上限({upper})",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)


# N6: 实战例句校验（仅对 mnemonic_exam_app 维度生效）
_EXAM_SENTENCE_MIN_WORDS = 8
_EXAM_SENTENCE_MAX_WORDS = 15
_CHINESE_RE = re.compile("[一-鿿]")
_WORD_TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _word_appears_in_sentence(target: str, sentence: str) -> bool:
    """检查目标词是否出现在英文例句中（含简单词形变化：s/es/ed/ing/ies/ied）.

    支持：原型、复数 (cat→cats)、过去式/分词 (study→studied, make→making)、
    y→i 变化 (study→studies/studied)、单字母 e 脱落 (make→making).
    不支持：不规则变化 (leaf→leaves, go→went) — 需 prompt 强制使用原型.
    """
    target_lower = target.lower()
    tokens = [m.group(0).lower() for m in _WORD_TOKEN_RE.finditer(sentence)]
    if target_lower in tokens:
        return True
    for tok in tokens:
        for suffix in ("ies", "ied", "ing", "es", "ed", "s"):
            if not tok.endswith(suffix):
                continue
            stem = tok[: -len(suffix)]
            if stem == target_lower:
                return True
            if stem + "e" == target_lower:  # making → make
                return True
            if suffix in ("ies", "ied") and stem + "y" == target_lower:  # studies → study
                return True
    return False


@RuleRegistry.register_layer1
class N6ExamSentence(_RuleCheckerBase):
    """N6: 实战例句校验（仅 mnemonic_exam_app 维度）.

    检查项：非空 / 纯英文 / 词数 8-15 / 含目标词（含简单词形变化）.
    其他 mnemonic 维度直接 pass.
    """

    rule_id = "N6"
    dimension = "mnemonic"
    description = "实战例句校验（仅 mnemonic_exam_app）"

    def check(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        if kwargs.get("dimension", "") != "mnemonic_exam_app":
            return RuleResult(rule_id=self.rule_id, passed=True)

        if not content:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="缺少助记内容")

        data = _parse_mnemonic_json(content)
        if data is None:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="助记内容不是合法 JSON 格式")

        sentence = str(data.get("exam_sentence", "")).strip()
        if not sentence:
            return RuleResult(rule_id=self.rule_id, passed=False, detail="exam_sentence 字段为空")

        if _CHINESE_RE.search(sentence):
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"exam_sentence 含中文字符: {sentence!r}",
            )

        word_count = len(_WORD_TOKEN_RE.findall(sentence))
        if word_count < _EXAM_SENTENCE_MIN_WORDS or word_count > _EXAM_SENTENCE_MAX_WORDS:
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=(
                    f"exam_sentence 词数({word_count})不在 "
                    f"{_EXAM_SENTENCE_MIN_WORDS}-{_EXAM_SENTENCE_MAX_WORDS} 范围"
                ),
            )

        if not _word_appears_in_sentence(word, sentence):
            return RuleResult(
                rule_id=self.rule_id, passed=False,
                detail=f"exam_sentence 不含目标词 {word!r}: {sentence!r}",
            )

        return RuleResult(rule_id=self.rule_id, passed=True)
