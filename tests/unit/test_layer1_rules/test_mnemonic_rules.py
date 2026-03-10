"""Mnemonic 规则单元测试（JSON 格式）."""

import json

import pytest

from vocab_qc.core.qc.layer1.mnemonic_rules import (
    N1MnemonicType,
    N2StructureCompleteness,
    N3FormulaSymbol,
    N4FormulaLength,
    N5TeacherScriptLength,
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

    def test_empty_script(self):
        result = self.checker.check(_mj(script=""), "kind")
        assert not result.passed
