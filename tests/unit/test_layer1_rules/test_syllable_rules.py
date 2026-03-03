"""Syllable 规则单元测试."""

import pytest

from vocab_qc.core.qc.layer1.syllable_rules import S1VowelAnchor, S2Separator, S3AtomicUnitIntegrity, S4SingleSyllableNoSplit


class TestS1VowelAnchor:
    def setup_method(self):
        self.checker = S1VowelAnchor()

    def test_single_syllable(self):
        result = self.checker.check("", "kind", syllables="kind")
        assert result.passed

    def test_two_syllables(self):
        result = self.checker.check("", "paper", syllables="pa·per")
        assert result.passed

    def test_three_syllables(self):
        result = self.checker.check("", "beautiful", syllables="beau·ti·ful")
        assert result.passed

    def test_le_exception(self):
        result = self.checker.check("", "table", syllables="ta·ble")
        assert result.passed

    def test_no_vowel_fails(self):
        result = self.checker.check("", "test", syllables="tst·e")
        assert not result.passed

    def test_empty_fails(self):
        result = self.checker.check("", "test", syllables="")
        assert not result.passed


class TestS2Separator:
    def setup_method(self):
        self.checker = S2Separator()

    def test_correct_separator(self):
        # U+00B7 中圆点
        result = self.checker.check("", "paper", syllables="pa\u00b7per")
        assert result.passed

    def test_single_syllable_no_separator(self):
        result = self.checker.check("", "kind", syllables="kind")
        assert result.passed

    def test_hyphen_fails(self):
        result = self.checker.check("", "paper", syllables="pa-per")
        assert not result.passed

    def test_dot_fails(self):
        result = self.checker.check("", "paper", syllables="pa.per")
        assert not result.passed

    def test_bullet_fails(self):
        # U+2022 bullet
        result = self.checker.check("", "paper", syllables="pa\u2022per")
        assert not result.passed


class TestS3AtomicUnitIntegrity:
    def setup_method(self):
        self.checker = S3AtomicUnitIntegrity()

    def test_no_split(self):
        result = self.checker.check("", "teacher", syllables="teach·er")
        assert result.passed

    def test_single_syllable(self):
        result = self.checker.check("", "ship", syllables="ship")
        assert result.passed

    def test_sh_split_fails(self):
        # s and h split across boundary
        result = self.checker.check("", "ashort", syllables="as·hort")
        assert not result.passed

    def test_th_split_fails(self):
        result = self.checker.check("", "nothing", syllables="not·hing")
        assert not result.passed

    def test_correct_boundary(self):
        result = self.checker.check("", "sunset", syllables="sun·set")
        assert result.passed


class TestS4SingleSyllableNoSplit:
    def setup_method(self):
        self.checker = S4SingleSyllableNoSplit()

    def test_single_syllable_no_split(self):
        result = self.checker.check("", "kind", syllables="kind", ipa="/kaɪnd/")
        assert result.passed

    def test_multi_syllable_with_split(self):
        result = self.checker.check("", "paper", syllables="pa·per", ipa="/ˈpeɪ·pər/")
        assert result.passed

    def test_single_ipa_but_split_fails(self):
        result = self.checker.check("", "kind", syllables="ki·nd", ipa="/kaɪnd/")
        assert not result.passed

    def test_no_ipa_single_part(self):
        result = self.checker.check("", "kind", syllables="kind")
        assert result.passed
