"""Mnemonic 规则单元测试（JSON 格式）."""

import json

from vocab_qc.core.qc.layer1.mnemonic_rules import (
    N1MnemonicType,
    N2StructureCompleteness,
    N3FormulaSymbol,
    N4FormulaLength,
    N5TeacherScriptLength,
    N6ExamSentence,
    count_logical_chars,
)


def _mj(formula: str = "a + b", chant: str = "记住", script: str = "这" * 500) -> str:
    """构造助记 JSON 字符串."""
    return json.dumps({"formula": formula, "chant": chant, "script": script}, ensure_ascii=False)


def _mj_exam(
    formula: str = "consistent(adj.) + with = 一致",
    chant: str = "consistent后锁with",
    exam_sentence: str = "His words are consistent with his actions in every situation.",
    script: str = "字" * 220,
) -> str:
    """构造 mnemonic_exam_app 助记 JSON（含 exam_sentence 字段）."""
    return json.dumps(
        {"formula": formula, "chant": chant, "exam_sentence": exam_sentence, "script": script},
        ensure_ascii=False,
    )


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
        """中英混排：'站(stand)稳的旗帜即标准。' → 中文8 + 英文1 = 9（标点不计）."""
        chant = "站(stand)稳的旗帜即标准。"
        assert count_logical_chars(chant) == 9
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
        # 默认维度（词中词/词根词缀）下限 500
        result = self.checker.check(_mj(script="字" * 500), "kind")
        assert result.passed

    def test_above_old_upper_bound_still_passes(self):
        # 移除上限后，超过原上限 600 仍通过
        result = self.checker.check(_mj(script="字" * 800), "kind")
        assert result.passed

    def test_too_short(self):
        # 默认维度下限 500，499 应失败
        result = self.checker.check(_mj(script="字" * 499), "kind")
        assert not result.passed

    def test_mixed_text_script_length(self):
        """话术中英混排：英文单词按 1 计数（默认维度下限 500）."""
        # 498 中文 + 1 英文单词 "hello" = logical 499 → 低于下限 500
        script_short = "字" * 498 + "hello"
        result = self.checker.check(_mj(script=script_short), "kind")
        assert not result.passed

        # 499 中文 + 1 英文单词 = logical 500 → 刚好达到下限
        script_ok = "字" * 499 + "hello"
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
        # "hello world" → 2 个英文词（空格不计）
        assert count_logical_chars("hello world") == 2

    def test_mixed_chinese_english(self):
        # "站(stand)稳的旗帜即标准。" → 中文8 + 英文1 = 9（标点不计）
        assert count_logical_chars("站(stand)稳的旗帜即标准。") == 9

    def test_english_in_parentheses(self):
        # "好(good)的" → 中文2 + 英文1 = 3（括号不计）
        assert count_logical_chars("好(good)的") == 3

    def test_multiple_english_words_in_chinese(self):
        # "the big dog很大" → 英文3 + 中文2 = 5（空格不计）
        assert count_logical_chars("the big dog很大") == 5

    def test_empty_string(self):
        assert count_logical_chars("") == 0

    def test_numbers_and_punctuation(self):
        # 纯数字和标点不计
        assert count_logical_chars("123") == 0
        assert count_logical_chars("!@#") == 0

    def test_mixed_with_numbers(self):
        # "hello123" → 英文1（hello算英文词，123不计）
        assert count_logical_chars("hello123") == 1


class TestN5ExamAppBounds:
    """N5 在 mnemonic_exam_app 维度的边界：下限 175，无上限."""

    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_exam_app_at_lower_bound_175_passes(self):
        result = self.checker.check(_mj(script="字" * 175), "x", dimension="mnemonic_exam_app")
        assert result.passed

    def test_exam_app_old_upper_250_passes(self):
        result = self.checker.check(_mj(script="字" * 250), "x", dimension="mnemonic_exam_app")
        assert result.passed

    def test_exam_app_below_lower_fails(self):
        result = self.checker.check(_mj(script="字" * 174), "x", dimension="mnemonic_exam_app")
        assert not result.passed
        assert "下限" in result.detail

    def test_exam_app_above_old_upper_passes(self):
        # 上限已移除：500 字仍应通过
        result = self.checker.check(_mj(script="字" * 500), "x", dimension="mnemonic_exam_app")
        assert result.passed


class TestN5SoundMeaningBounds:
    """N5 在 mnemonic_sound_meaning 维度的边界：下限 175，无上限（1v1 私教风格升级）."""

    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_sound_meaning_at_lower_bound_175_passes(self):
        result = self.checker.check(_mj(script="字" * 175), "x", dimension="mnemonic_sound_meaning")
        assert result.passed

    def test_sound_meaning_old_upper_250_passes(self):
        result = self.checker.check(_mj(script="字" * 250), "x", dimension="mnemonic_sound_meaning")
        assert result.passed

    def test_sound_meaning_below_lower_fails(self):
        result = self.checker.check(_mj(script="字" * 174), "x", dimension="mnemonic_sound_meaning")
        assert not result.passed
        assert "下限" in result.detail

    def test_sound_meaning_above_old_upper_passes(self):
        # 上限已移除：500 字仍应通过
        result = self.checker.check(_mj(script="字" * 500), "x", dimension="mnemonic_sound_meaning")
        assert result.passed


class TestN5RootAffixBounds:
    """N5 在 mnemonic_root_affix 维度的边界：下限 175，无上限（1v1 私教风格升级）."""

    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_root_affix_at_lower_bound_175_passes(self):
        result = self.checker.check(_mj(script="字" * 175), "x", dimension="mnemonic_root_affix")
        assert result.passed

    def test_root_affix_old_upper_250_passes(self):
        result = self.checker.check(_mj(script="字" * 250), "x", dimension="mnemonic_root_affix")
        assert result.passed

    def test_root_affix_below_lower_fails(self):
        result = self.checker.check(_mj(script="字" * 174), "x", dimension="mnemonic_root_affix")
        assert not result.passed
        assert "下限" in result.detail

    def test_root_affix_above_old_upper_passes(self):
        # 上限已移除：500 字仍应通过
        result = self.checker.check(_mj(script="字" * 500), "x", dimension="mnemonic_root_affix")
        assert result.passed


class TestN5WordInWordBounds:
    """N5 在 mnemonic_word_in_word 维度的边界：下限 175，无上限（1v1 私教风格升级）."""

    def setup_method(self):
        self.checker = N5TeacherScriptLength()

    def test_word_in_word_at_lower_bound_175_passes(self):
        result = self.checker.check(_mj(script="字" * 175), "x", dimension="mnemonic_word_in_word")
        assert result.passed

    def test_word_in_word_old_upper_250_passes(self):
        result = self.checker.check(_mj(script="字" * 250), "x", dimension="mnemonic_word_in_word")
        assert result.passed

    def test_word_in_word_below_lower_fails(self):
        result = self.checker.check(_mj(script="字" * 174), "x", dimension="mnemonic_word_in_word")
        assert not result.passed
        assert "下限" in result.detail

    def test_word_in_word_above_old_upper_passes(self):
        # 上限已移除：500 字仍应通过
        result = self.checker.check(_mj(script="字" * 500), "x", dimension="mnemonic_word_in_word")
        assert result.passed


class TestN6ExamSentence:
    def setup_method(self):
        self.checker = N6ExamSentence()

    def test_other_dimension_passes(self):
        # 非 mnemonic_exam_app 维度直接 pass，无论 exam_sentence 是否存在
        result = self.checker.check(_mj(), "kind", dimension="mnemonic_root_affix")
        assert result.passed
        # 即使无 dimension 参数也 pass（默认非 exam_app）
        result = self.checker.check(_mj(), "kind")
        assert result.passed

    def test_valid_exam_sentence(self):
        result = self.checker.check(_mj_exam(), "consistent", dimension="mnemonic_exam_app")
        assert result.passed

    def test_empty_sentence_fails(self):
        result = self.checker.check(_mj_exam(exam_sentence=""), "consistent", dimension="mnemonic_exam_app")
        assert not result.passed
        assert "为空" in result.detail

    def test_missing_field_fails(self):
        # JSON 不含 exam_sentence 键 → 视为空
        bad = json.dumps({"formula": "a+b", "chant": "x", "script": "y" * 220}, ensure_ascii=False)
        result = self.checker.check(bad, "consistent", dimension="mnemonic_exam_app")
        assert not result.passed

    def test_chinese_in_sentence_fails(self):
        result = self.checker.check(
            _mj_exam(exam_sentence="His 言行 are consistent with his actions every day."),
            "consistent", dimension="mnemonic_exam_app",
        )
        assert not result.passed
        assert "中文" in result.detail

    def test_too_few_words_fails(self):
        # 7 词 < 下限 8
        result = self.checker.check(
            _mj_exam(exam_sentence="He is consistent with his actions every day."),
            "consistent", dimension="mnemonic_exam_app",
        )
        # 上面恰好 9 词，需要构造 7 词的
        result = self.checker.check(
            _mj_exam(exam_sentence="He is consistent with his actions today."),
            "consistent", dimension="mnemonic_exam_app",
        )
        assert not result.passed
        assert "词数" in result.detail

    def test_too_many_words_fails(self):
        # 16 词 > 上限 15
        sentence = " ".join(["word"] * 15) + " consistent."
        result = self.checker.check(
            _mj_exam(exam_sentence=sentence), "consistent", dimension="mnemonic_exam_app",
        )
        assert not result.passed
        assert "词数" in result.detail

    def test_target_word_missing_fails(self):
        # 例句不含目标词
        result = self.checker.check(
            _mj_exam(exam_sentence="The cat is sitting on the mat by the door."),
            "consistent", dimension="mnemonic_exam_app",
        )
        assert not result.passed
        assert "不含目标词" in result.detail

    def test_target_word_inflection_plural(self):
        # 复数形式 cats
        result = self.checker.check(
            _mj_exam(exam_sentence="The cats are sitting on the mat by the door."),
            "cat", dimension="mnemonic_exam_app",
        )
        assert result.passed

    def test_target_word_inflection_past_tense(self):
        # 过去式 studied (study)
        result = self.checker.check(
            _mj_exam(exam_sentence="She studied hard for the exam yesterday afternoon and night."),
            "study", dimension="mnemonic_exam_app",
        )
        assert result.passed

    def test_target_word_inflection_ing(self):
        # 现在分词 making (make)
        result = self.checker.check(
            _mj_exam(exam_sentence="He is making a plan for the upcoming exam this week."),
            "make", dimension="mnemonic_exam_app",
        )
        assert result.passed

    def test_target_word_case_insensitive(self):
        result = self.checker.check(
            _mj_exam(exam_sentence="CONSISTENT with his actions, he completed the task on time."),
            "consistent", dimension="mnemonic_exam_app",
        )
        assert result.passed

    def test_invalid_json_fails(self):
        result = self.checker.check("not json", "x", dimension="mnemonic_exam_app")
        assert not result.passed

    def test_empty_content_fails(self):
        result = self.checker.check("", "x", dimension="mnemonic_exam_app")
        assert not result.passed
