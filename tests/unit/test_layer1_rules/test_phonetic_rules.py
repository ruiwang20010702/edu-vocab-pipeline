"""Phonetic 规则单元测试."""

import pytest

from vocab_qc.core.qc.layer1.phonetic_rules import P1IpaFormat, P2IpaSyllableAlignment


class TestP1IpaFormat:
    def setup_method(self):
        self.checker = P1IpaFormat()

    def test_valid_ipa(self):
        result = self.checker.check("", "kind", ipa="/kaɪnd/")
        assert result.passed

    def test_valid_ipa_with_dot(self):
        result = self.checker.check("", "paper", ipa="/ˈpeɪ·pər/")
        assert result.passed

    def test_valid_ipa_with_stress(self):
        result = self.checker.check("", "about", ipa="/əˈbaʊt/")
        assert result.passed

    def test_missing_slashes(self):
        result = self.checker.check("", "kind", ipa="kaɪnd")
        assert not result.passed

    def test_empty_ipa(self):
        result = self.checker.check("", "kind", ipa="")
        assert not result.passed

    def test_only_opening_slash(self):
        result = self.checker.check("", "kind", ipa="/kaɪnd")
        assert not result.passed


class TestP2IpaSyllableAlignment:
    def setup_method(self):
        self.checker = P2IpaSyllableAlignment()

    def test_single_syllable_aligned(self):
        result = self.checker.check("", "kind", ipa="/kaɪnd/", syllables="kind")
        assert result.passed

    def test_two_syllable_aligned(self):
        result = self.checker.check("", "paper", ipa="/ˈpeɪ·pər/", syllables="pa·per")
        assert result.passed

    def test_three_syllable_aligned(self):
        result = self.checker.check("", "beautiful", ipa="/ˈbjuː·tɪ·fəl/", syllables="beau·ti·ful")
        assert result.passed

    def test_misaligned_syllables(self):
        result = self.checker.check("", "paper", ipa="/ˈpeɪpər/", syllables="pa·per")
        assert not result.passed

    def test_missing_ipa(self):
        result = self.checker.check("", "kind", ipa="", syllables="kind")
        assert not result.passed

    def test_missing_syllables(self):
        result = self.checker.check("", "kind", ipa="/kaɪnd/", syllables="")
        assert not result.passed
