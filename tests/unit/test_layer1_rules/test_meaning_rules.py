"""Meaning 规则单元测试."""

import pytest
from vocab_qc.core.qc.layer1.meaning_rules import (
    M3PosTagFormat,
    M4PosNewlineSeparation,
    M5SemicolonSeparation,
    M6NoBrackets,
)


class TestM3PosTagFormat:
    def setup_method(self):
        self.checker = M3PosTagFormat()

    @pytest.mark.parametrize("pos", ["n.", "v.", "adj.", "adv.", "prep.", "conj.", "pron.", "num.", "art.", "int."])
    def test_valid_pos_tags(self, pos):
        result = self.checker.check("友好的", "kind", pos=pos)
        assert result.passed

    @pytest.mark.parametrize("pos", ["noun", "verb", "n", "adj", "", "名词"])
    def test_invalid_pos_tags(self, pos):
        result = self.checker.check("友好的", "kind", pos=pos)
        assert not result.passed

    def test_missing_pos(self):
        result = self.checker.check("友好的", "kind")
        assert not result.passed


class TestM4PosNewlineSeparation:
    def setup_method(self):
        self.checker = M4PosNewlineSeparation()

    def test_single_pos_passes(self):
        result = self.checker.check("adj. 友好的", "kind")
        assert result.passed

    def test_multi_pos_on_separate_lines(self):
        result = self.checker.check("adj. 友好的\nn. 种类", "kind")
        assert result.passed

    def test_multi_pos_on_same_line_fails(self):
        result = self.checker.check("adj. 友好的 n. 种类", "kind")
        assert not result.passed

    def test_empty_content(self):
        result = self.checker.check("", "kind")
        assert result.passed  # 无内容不报错


class TestM5SemicolonSeparation:
    def setup_method(self):
        self.checker = M5SemicolonSeparation()

    def test_single_meaning_passes(self):
        result = self.checker.check("", "kind", meaning="友好的")
        assert result.passed

    def test_semicolon_separated(self):
        result = self.checker.check("", "kind", meaning="友好的；善良的")
        assert result.passed

    def test_comma_separated_fails(self):
        result = self.checker.check("", "kind", meaning="友好的，善良的")
        assert not result.passed

    def test_no_meaning(self):
        result = self.checker.check("", "kind", meaning="")
        assert result.passed


class TestM6NoBrackets:
    def setup_method(self):
        self.checker = M6NoBrackets()

    def test_no_brackets_passes(self):
        result = self.checker.check("", "kind", meaning="友好的")
        assert result.passed

    def test_english_brackets_fail(self):
        result = self.checker.check("", "kind", meaning="友好的(形容词)")
        assert not result.passed

    def test_chinese_brackets_fail(self):
        result = self.checker.check("", "kind", meaning="友好的（形容词）")
        assert not result.passed

    def test_only_paren_fail(self):
        result = self.checker.check("", "kind", meaning="(友好的)")
        assert not result.passed
