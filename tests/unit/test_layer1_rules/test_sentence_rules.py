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

    def test_contains_word_ing_form(self):
        """基础 -ing 变形."""
        result = self.checker.check("She is playing the piano.", "play")
        assert result.passed

    def test_contains_word_e_drop_ing(self):
        """-e 结尾去 e 加 -ing (make → making)."""
        result = self.checker.check("She is making a cake.", "make")
        assert result.passed

    def test_contains_word_e_drop_ed(self):
        """-e 结尾去 e 加 -ed (love → loved)."""
        result = self.checker.check("She loved the gift.", "love")
        assert result.passed

    def test_contains_word_double_consonant_ing(self):
        """辅元辅双写加 -ing (run → running)."""
        result = self.checker.check("He is running fast.", "run")
        assert result.passed

    def test_contains_word_double_consonant_ed(self):
        """辅元辅双写加 -ed (stop → stopped)."""
        result = self.checker.check("The bus stopped here.", "stop")
        assert result.passed

    def test_contains_word_y_to_ies(self):
        """-y 结尾变 -ies (study → studies)."""
        result = self.checker.check("She studies hard every day.", "study")
        assert result.passed

    def test_contains_word_y_to_ied(self):
        """-y 结尾变 -ied (study → studied)."""
        result = self.checker.check("He studied math yesterday.", "study")
        assert result.passed

    def test_contains_word_y_to_ier(self):
        """-y 结尾变 -ier (happy → happier)."""
        result = self.checker.check("She is happier than before.", "happy")
        assert result.passed

    def test_contains_word_y_to_iest(self):
        """-y 结尾变 -iest (happy → happiest)."""
        result = self.checker.check("He is the happiest boy.", "happy")
        assert result.passed

    def test_contains_word_y_to_ily(self):
        """-y 结尾变 -ily (happy → happily)."""
        result = self.checker.check("She smiled happily.", "happy")
        assert result.passed

    def test_contains_word_es_suffix(self):
        """-es 变形 (go → goes)."""
        result = self.checker.check("She goes to school.", "go")
        assert result.passed

    def test_contains_word_er_suffix(self):
        """-er 变形 (kind → kinder)."""
        result = self.checker.check("She is kinder than him.", "kind")
        assert result.passed

    def test_contains_word_est_suffix(self):
        """-est 变形 (kind → kindest)."""
        result = self.checker.check("She is the kindest person.", "kind")
        assert result.passed

    def test_contains_word_ly_suffix(self):
        """-ly 变形 (kind → kindly)."""
        result = self.checker.check("She spoke kindly to the child.", "kind")
        assert result.passed

    def test_case_insensitive(self):
        """大小写不敏感匹配."""
        result = self.checker.check("Kind people are welcome.", "kind")
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

    def test_empty_content(self):
        result = self.checker.check("", "kind")
        assert not result.passed
        assert "缺少例句" in result.detail

    def test_multiline_only_first_line(self):
        """多行时只取第一行计算长度."""
        result = self.checker.check("She is always very kind.\n这是中文翻译。", "kind")
        assert result.passed  # 5 words in first line

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
