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

    # 旧带点格式（向后兼容）
    @pytest.mark.parametrize(
        "pos",
        ["n.", "v.", "adj.", "adv.", "prep.", "conj.", "pron.", "num.", "art.", "int."],
    )
    def test_valid_legacy_pos_tags(self, pos):
        result = self.checker.check("友好的", "kind", pos=pos)
        assert result.passed

    # 新规范不带点格式（含 mod/aux/abbr/det 等新增 + n phr/a phr 短语标签）
    @pytest.mark.parametrize(
        "pos",
        [
            "n", "v", "adj", "adv", "prep", "pron", "num",
            "mod", "aux", "conj", "int", "abbr", "det",
            "phr", "n phr", "a phr",
        ],
    )
    def test_valid_new_pos_tags(self, pos):
        result = self.checker.check("友好的", "kind", pos=pos)
        assert result.passed

    @pytest.mark.parametrize("pos", ["noun", "verb", "x", "", "名词", "n.phr", "n_phr"])
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

    # ---- 长短标签消歧（核心回归：n phr / a phr 等含空格的标签） ----
    def test_n_phr_single_line_passes(self):
        # 'n phr' 必须优先于 'n' 匹配，否则会被误判为多词性
        result = self.checker.check("n phr 名词短语示例", "look forward to")
        assert result.passed

    def test_a_phr_single_line_passes(self):
        result = self.checker.check("a phr 形容词短语", "as easy as pie")
        assert result.passed

    def test_n_phr_multi_lines_passes(self):
        result = self.checker.check("n phr 名词短语\nv. 动词义", "kind")
        assert result.passed

    def test_n_phr_with_other_pos_same_line_fails(self):
        # 即便 n phr 优先匹配，同行还有 v. 也应被识别为多词性
        result = self.checker.check("n phr 短语 v. 动词", "kind")
        assert not result.passed

    # ---- 后行断言：普通单词首字母不应误匹配单字符 POS ----
    def test_normal_word_does_not_match_single_char_pos(self):
        # apple 中的 'a'、not 中的 'n' 都不应被识别为 POS
        result = self.checker.check("apple is a fruit", "apple")
        assert result.passed

    def test_text_with_isolated_a_treated_as_single_match(self):
        # 'not a word' 里 'a' 是孤立字母，会算 1 个匹配，但不超过 1 个 → 通过
        result = self.checker.check("not a word", "kind")
        assert result.passed

    # ---- 新格式与旧格式混合 ----
    def test_new_format_single_line_passes(self):
        result = self.checker.check("adj 友好的", "kind")
        assert result.passed

    def test_new_format_multi_pos_same_line_fails(self):
        result = self.checker.check("adj 友好的 n 种类", "kind")
        assert not result.passed


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
