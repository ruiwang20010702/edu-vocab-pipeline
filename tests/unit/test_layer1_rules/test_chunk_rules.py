"""Chunk 规则单元测试."""

import pytest

from vocab_qc.core.qc.layer1.chunk_rules import C1ChunkContainsWord, C2ChunkLength, C4NoBrackets, C5ChineseOnSeparateLine


class TestC1ChunkContainsWord:
    def setup_method(self):
        self.checker = C1ChunkContainsWord()

    def test_contains_word_directly(self):
        result = self.checker.check("be kind to sb.", "kind")
        assert result.passed

    def test_contains_word_case_insensitive(self):
        result = self.checker.check("Kind regards", "kind")
        assert result.passed

    def test_contains_word_plural(self):
        result = self.checker.check("many kinds of", "kind")
        assert result.passed

    def test_contains_word_ing_form(self):
        result = self.checker.check("running fast", "run")
        assert result.passed

    def test_missing_word(self):
        result = self.checker.check("be nice to sb.", "kind")
        assert not result.passed

    def test_empty_content(self):
        result = self.checker.check("", "kind")
        assert not result.passed

    def test_empty_word(self):
        result = self.checker.check("be kind to sb.", "")
        assert not result.passed


class TestC2ChunkLength:
    def setup_method(self):
        self.checker = C2ChunkLength()

    def test_two_words(self):
        result = self.checker.check("kind regards", "kind")
        assert result.passed

    def test_five_words(self):
        result = self.checker.check("be kind to each other", "kind")
        assert result.passed

    def test_three_words(self):
        result = self.checker.check("a kind of", "kind")
        assert result.passed

    def test_one_word_fails(self):
        result = self.checker.check("kind", "kind")
        assert not result.passed

    def test_six_words_fails(self):
        result = self.checker.check("be very kind to each other", "kind")
        assert not result.passed

    def test_empty_fails(self):
        result = self.checker.check("", "kind")
        assert not result.passed


class TestC4NoBrackets:
    def setup_method(self):
        self.checker = C4NoBrackets()

    def test_no_brackets(self):
        result = self.checker.check("be kind to sb.", "kind")
        assert result.passed

    def test_english_brackets_fail(self):
        result = self.checker.check("be kind (to sb.)", "kind")
        assert not result.passed

    def test_chinese_brackets_fail(self):
        result = self.checker.check("be kind（对某人）", "kind")
        assert not result.passed

    def test_clean_content(self):
        result = self.checker.check("a kind of", "kind")
        assert result.passed


class TestC5ChineseOnSeparateLine:
    def setup_method(self):
        self.checker = C5ChineseOnSeparateLine()

    def test_english_only_passes(self):
        result = self.checker.check("be kind to sb.", "kind")
        assert result.passed

    def test_chinese_mixed_in_fails(self):
        result = self.checker.check("be kind 友好的", "kind")
        assert not result.passed

    def test_with_separate_cn_field(self):
        result = self.checker.check("be kind to sb.", "kind", content_cn="对某人友好")
        assert result.passed

    def test_sb_sth_not_chinese(self):
        result = self.checker.check("be kind to sb.", "kind")
        assert result.passed
