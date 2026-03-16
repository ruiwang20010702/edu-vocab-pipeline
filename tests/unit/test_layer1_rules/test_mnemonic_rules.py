"""Mnemonic 规则单元测试（JSON 格式）."""

import json

from vocab_qc.core.qc.layer1.mnemonic_rules import (
    N1MnemonicType,
    N2StructureCompleteness,
    N3FormulaSymbol,
    N4FormulaLength,
    N5TeacherScriptLength,
    count_logical_chars,
)


def _mj(formula: str = "a + b", chant: str = "记住", script: str = "这" * 500) -> str:
    """构造助记 JSON 字符串."""
    return json.dumps({"formula": formula, "chant": chant, "script": script}, ensure_ascii=False)


VALID_MNEMONIC = _mj(formula="kind = k + ind", chant="kind里藏着king", script="这" * 500)


class TestN1MnemonicType:
    def setup_method(self):
        self.checker = N1MnemonicType()

    def test_valid_json(self):
        result = self.checker.check(VALID_MNEMONIC, "kind")
        assert result.passed

    def test_invalid_json(self):
        result = self.checker.check("这不是JSON", "kind")
        assert not result.passed
        assert "JSON" in result.detail

    def test_missing_keys(self):
        result = self.checker.check('{"formula": "a+b"}', "kind")
        assert not result.passed
        assert "chant" in result.detail

    def test_empty_content(self):
        result = self.checker.check("", "kind")
        assert not result.passed


class TestN2StructureCompleteness:
    def setup_method(self):
        self.checker = N2StructureCompleteness()

    def test_complete_structure(self):
        result = self.checker.check(VALID_MNEMONIC, "kind")
        assert result.passed

    def test_empty_formula(self):
        result = self.checker.check(_mj(formula=""), "kind")
        assert not result.passed
        assert "formula" in result.detail

    def test_empty_chant(self):
        result = self.checker.check(_mj(chant=""), "kind")
        assert not result.passed
        assert "chant" in result.detail

    def test_empty_script(self):
        result = self.checker.check(_mj(script=""), "kind")
        assert not result.passed
        assert "script" in result.detail

    def test_all_empty(self):
        result = self.checker.check(_mj(formula="", chant="", script=""), "kind")
        assert not result.passed


class TestN3FormulaSymbol:
    def setup_method(self):
        self.checker = N3FormulaSymbol()

    def test_plus_symbol(self):
        result = self.checker.check(_mj(formula="kind = k + ind"), "kind")
        assert result.passed

    def test_approx_symbol(self):
        result = self.checker.check(_mj(formula="kind ≈ king"), "kind")
        assert result.passed

    def test_equals_symbol(self):
        result = self.checker.check(_mj(formula="kind = k + ind"), "kind")
        assert result.passed

    def test_no_symbol_fails(self):
        result = self.checker.check(_mj(formula="kind 拆解为 k ind"), "kind")
        assert not result.passed

    def test_empty_formula(self):
        result = self.checker.check(_mj(formula=""), "kind")
        assert not result.passed


class TestN4FormulaLength:
    def setup_method(self):
        self.checker = N4FormulaLength()

    def test_short_slogan(self):
        result = self.checker.check(_mj(chant="kind藏着king"), "kind")
        assert result.passed

    def test_exactly_15_chars(self):
        result = self.checker.check(_mj(chant="字" * 15), "kind")
        assert result.passed

    def test_over_15_chars(self):
        result = self.checker.check(_mj(chant="字" * 16), "kind")
        assert not result.passed

    def test_exam_type_allows_30(self):
        result = self.checker.check(_mj(chant="字" * 25), "kind", dimension="mnemonic_exam_app")
        assert result.passed

    def test_exam_type_over_30_fails(self):
        result = self.checker.check(_mj(chant="字" * 31), "kind", dimension="mnemonic_exam_app")
        assert not result.passed

    def test_mixed_text_counts_word_as_one(self):
        """中英混排：'站(stand)稳的旗帜即标准。' len=18, logical=12, 应通过."""
        chant = "站(stand)稳的旗帜即标准。"
        assert count_logical_chars(chant) == 12
        result = self.checker.check(_mj(chant=chant), "standard")
        assert result.passed

    def test_mixed_text_over_limit(self):
        """中英混排超限：14中文+1英文单词 = logical 15 通过，16中文+1英文 = 17 不通过."""
        chant_ok = "字" * 14 + "a"  # logical = 15
        result = self.checker.check(_mj(chant=chant_ok), "w")
        assert result.passed

        chant_fail = "字" * 15 + "a"  # logical = 16
        result = self.checker.check(_mj(chant=chant_fail), "w")
        assert not result.passed

    def test_empty_chant_fails(self):
        result = self.checker.check(_mj(chant=""), "kind")
        assert not result.passed


class TestN5TeacherScriptLength:
    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_target_length(self):
        result = self.checker.check(_mj(script="字" * 500), "kind")
        assert result.passed

    def test_lower_bound(self):
        result = self.checker.check(_mj(script="字" * 400), "kind")
        assert result.passed

    def test_upper_bound(self):
        result = self.checker.check(_mj(script="字" * 600), "kind")
        assert result.passed

    def test_too_short(self):
        result = self.checker.check(_mj(script="字" * 300), "kind")
        assert not result.passed

    def test_too_long(self):
        result = self.checker.check(_mj(script="字" * 700), "kind")
        assert not result.passed

    def test_mixed_text_script_length(self):
        """话术中英混排：英文单词按 1 计数."""
        # 398 中文 + 1 英文单词 "hello" = logical 399 → 低于下限 400
        script_short = "字" * 398 + "hello"
        result = self.checker.check(_mj(script=script_short), "kind")
        assert not result.passed

        # 399 中文 + 1 英文单词 = logical 400 → 刚好达到下限
        script_ok = "字" * 399 + "hello"
        result = self.checker.check(_mj(script=script_ok), "kind")
        assert result.passed

    def test_empty_script(self):
        result = self.checker.check(_mj(script=""), "kind")
        assert not result.passed


class TestCountLogicalChars:
    def test_pure_chinese(self):
        assert count_logical_chars("你好世界") == 4

    def test_pure_english_single_word(self):
        assert count_logical_chars("hello") == 1

    def test_pure_english_multiple_words(self):
        # "hello world" → "¤ ¤" → 3
        assert count_logical_chars("hello world") == 3

    def test_mixed_chinese_english(self):
        # "站(stand)稳的旗帜即标准。" → "站(¤)稳的旗帜即标准。" → 12
        assert count_logical_chars("站(stand)稳的旗帜即标准。") == 12

    def test_english_in_parentheses(self):
        # "好(good)的" → "好(¤)的" → 5
        assert count_logical_chars("好(good)的") == 5

    def test_multiple_english_words_in_chinese(self):
        # "the big dog很大" → "¤ ¤ ¤很大" → 7
        assert count_logical_chars("the big dog很大") == 7

    def test_empty_string(self):
        assert count_logical_chars("") == 0

    def test_numbers_and_punctuation(self):
        assert count_logical_chars("123") == 3
        assert count_logical_chars("!@#") == 3

    def test_mixed_with_numbers(self):
        # "hello123" → "¤123" → 4 (英文算1，数字各算1)
        assert count_logical_chars("hello123") == 4
