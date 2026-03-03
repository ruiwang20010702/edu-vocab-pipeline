"""Sentence 规则单元测试."""

import pytest

from vocab_qc.core.qc.layer1.sentence_rules import E6SentenceContainsWord, E7SentenceLength, E8HasChineseTranslation


class TestE6SentenceContainsWord:
    def setup_method(self):
        self.checker = E6SentenceContainsWord()

    def test_contains_word(self):
        result = self.checker.check("The teacher is always kind to every student.", "kind")
        assert result.passed

    def test_contains_word_plural(self):
        result = self.checker.check("There are many kinds of animals.", "kind")
        assert result.passed

    def test_contains_word_past_tense(self):
        result = self.checker.check("She played the piano yesterday.", "play")
        assert result.passed

    def test_missing_word(self):
        result = self.checker.check("The weather is nice today.", "kind")
        assert not result.passed

    def test_empty_sentence(self):
        result = self.checker.check("", "kind")
        assert not result.passed

    def test_empty_word(self):
        result = self.checker.check("The teacher is kind.", "")
        assert not result.passed


class TestE7SentenceLength:
    def setup_method(self):
        self.checker = E7SentenceLength()

    def test_min_length(self):
        result = self.checker.check("She is always very kind.", "kind")
        assert result.passed  # 5 words

    def test_five_words(self):
        result = self.checker.check("The teacher is very kind.", "kind")
        assert result.passed

    def test_twenty_words(self):
        sentence = " ".join(["word"] * 20)
        result = self.checker.check(sentence, "word")
        assert result.passed

    def test_too_short(self):
        result = self.checker.check("Be kind.", "kind")
        assert not result.passed

    def test_too_long(self):
        sentence = " ".join(["word"] * 21)
        result = self.checker.check(sentence, "word")
        assert not result.passed

    def test_normal_sentence(self):
        result = self.checker.check("The teacher is always kind to every student.", "kind")
        assert result.passed  # 8 words


class TestE8HasChineseTranslation:
    def setup_method(self):
        self.checker = E8HasChineseTranslation()

    def test_has_translation(self):
        result = self.checker.check("The teacher is kind.", "kind", content_cn="老师很友好。")
        assert result.passed

    def test_has_translation_with_punctuation(self):
        result = self.checker.check("Be kind.", "kind", content_cn="友好的。")
        assert result.passed

    def test_chinese_characters_present(self):
        result = self.checker.check("Hello.", "hello", content_cn="你好")
        assert result.passed

    def test_missing_translation(self):
        result = self.checker.check("The teacher is kind.", "kind", content_cn="")
        assert not result.passed

    def test_no_cn_kwarg(self):
        result = self.checker.check("The teacher is kind.", "kind")
        assert not result.passed

    def test_only_english_in_cn_field(self):
        result = self.checker.check("Hello.", "hello", content_cn="hello world")
        assert not result.passed
