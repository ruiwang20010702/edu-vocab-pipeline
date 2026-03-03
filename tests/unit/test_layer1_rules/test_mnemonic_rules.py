"""Mnemonic 规则单元测试."""

import pytest

from vocab_qc.core.qc.layer1.mnemonic_rules import (
    N1MnemonicType,
    N2StructureCompleteness,
    N3FormulaSymbol,
    N4FormulaLength,
    N5TeacherScriptLength,
)

VALID_MNEMONIC = """[词中词]
[核心公式] kind = k + ind
[助记口诀] kind藏着king
[老师话术] """ + "这" * 500


INCOMPLETE_MNEMONIC = """[词中词]
[核心公式] kind = k + ind
kind藏着king"""


class TestN1MnemonicType:
    def setup_method(self):
        self.checker = N1MnemonicType()

    @pytest.mark.parametrize("mtype", ["词根词缀", "词中词", "音义联想", "考试应用"])
    def test_valid_types(self, mtype):
        result = self.checker.check(f"[{mtype}]\n内容", "kind")
        assert result.passed

    def test_invalid_type(self):
        result = self.checker.check("[谐音记忆]\n内容", "kind")
        assert not result.passed

    def test_no_type_marker(self):
        result = self.checker.check("没有类型标记的内容", "kind")
        assert not result.passed

    def test_empty_content(self):
        result = self.checker.check("", "kind")
        assert not result.passed


class TestN2StructureCompleteness:
    def setup_method(self):
        self.checker = N2StructureCompleteness()

    def test_complete_structure(self):
        result = self.checker.check(VALID_MNEMONIC, "kind")
        assert result.passed

    def test_missing_type(self):
        content = "[核心公式] a+b\n[助记口诀] 记住\n[老师话术] 话术"
        result = self.checker.check(content, "kind")
        assert not result.passed

    def test_missing_formula(self):
        content = "[词中词]\n[助记口诀] 记住\n[老师话术] 话术"
        result = self.checker.check(content, "kind")
        assert not result.passed

    def test_incomplete_structure(self):
        result = self.checker.check(INCOMPLETE_MNEMONIC, "kind")
        assert not result.passed


class TestN3FormulaSymbol:
    def setup_method(self):
        self.checker = N3FormulaSymbol()

    def test_plus_symbol(self):
        result = self.checker.check("[核心公式] kind = k + ind\n其他", "kind")
        assert result.passed

    def test_approx_symbol(self):
        result = self.checker.check("[核心公式] kind ≈ king\n其他", "kind")
        assert result.passed

    def test_equals_symbol(self):
        result = self.checker.check("[核心公式] kind = k + ind\n其他", "kind")
        assert result.passed

    def test_no_symbol_fails(self):
        result = self.checker.check("[核心公式] kind 拆解为 k ind\n其他", "kind")
        assert not result.passed

    def test_no_formula_section(self):
        result = self.checker.check("没有公式部分", "kind")
        assert not result.passed


class TestN4FormulaLength:
    def setup_method(self):
        self.checker = N4FormulaLength()

    def test_short_slogan(self):
        result = self.checker.check("[助记口诀] kind藏着king\n[其他]", "kind")
        assert result.passed

    def test_exactly_15_chars(self):
        result = self.checker.check("[助记口诀] " + "字" * 15 + "\n[其他]", "kind")
        assert result.passed

    def test_over_15_chars(self):
        result = self.checker.check("[助记口诀] " + "字" * 16 + "\n[其他]", "kind")
        assert not result.passed

    def test_exam_type_allows_30(self):
        result = self.checker.check("[考试应用]\n[助记口诀] " + "字" * 25 + "\n[其他]", "kind")
        assert result.passed

    def test_exam_type_over_30_fails(self):
        result = self.checker.check("[考试应用]\n[助记口诀] " + "字" * 31 + "\n[其他]", "kind")
        assert not result.passed

    def test_no_slogan_fails(self):
        result = self.checker.check("没有口诀", "kind")
        assert not result.passed


class TestN5TeacherScriptLength:
    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_target_length(self):
        result = self.checker.check("[老师话术] " + "字" * 500, "kind")
        assert result.passed

    def test_lower_bound(self):
        result = self.checker.check("[老师话术] " + "字" * 400, "kind")
        assert result.passed

    def test_upper_bound(self):
        result = self.checker.check("[老师话术] " + "字" * 600, "kind")
        assert result.passed

    def test_too_short(self):
        result = self.checker.check("[老师话术] " + "字" * 300, "kind")
        assert not result.passed

    def test_too_long(self):
        result = self.checker.check("[老师话术] " + "字" * 700, "kind")
        assert not result.passed

    def test_no_script(self):
        result = self.checker.check("没有话术部分", "kind")
        assert not result.passed
