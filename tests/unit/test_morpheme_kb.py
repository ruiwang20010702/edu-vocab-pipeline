"""词根词缀知识库单元测试."""

import pytest

from vocab_qc.core.generators.morpheme_kb import (
    MorphemeEntry,
    _parse_prefix_forms,
    _parse_root_forms,
    _parse_suffix_forms,
    format_kb_for_prompt,
    get_morpheme_kb,
)


class TestParseRootForms:
    def test_with_bracket_variants(self):
        forms = _parse_root_forms("DUC, DUCT[DU]")
        assert "duc" in forms
        assert "duct" in forms
        assert "du" in forms

    def test_without_brackets(self):
        forms = _parse_root_forms("NORM")
        assert forms == ("norm",)

    def test_multiple_comma_separated(self):
        forms = _parse_root_forms("TAIN, TEN[TIN]")
        assert "tain" in forms
        assert "ten" in forms
        assert "tin" in forms


class TestParsePrefixForms:
    def test_with_paren_variants(self):
        forms = _parse_prefix_forms("AB (ABS, A)")
        assert "ab" in forms
        assert "abs" in forms
        assert "a" in forms

    def test_main_form_first(self):
        forms = _parse_prefix_forms("AB (ABS, A)")
        assert forms[0] == "ab"

    def test_many_variants(self):
        forms = _parse_prefix_forms("AD (AC, AS, AF, AG, AL, AN, AP, AR, AT, A)")
        assert "ad" in forms
        assert "ac" in forms
        assert "at" in forms


class TestParseSuffixForms:
    def test_comma_separated(self):
        forms = _parse_suffix_forms("AGE, ITY, TION")
        assert "age" in forms
        assert "ity" in forms
        assert "tion" in forms

    def test_with_dash(self):
        forms = _parse_suffix_forms("-AGE, -ITY, -TION")
        assert "age" in forms
        assert "ity" in forms

    def test_single(self):
        forms = _parse_suffix_forms("-ACY")
        assert forms == ("acy",)


class TestFormatKbForPrompt:
    def test_contains_sections(self):
        text = format_kb_for_prompt()
        assert "## 前缀" in text
        assert "## 词根" in text
        assert "## 后缀" in text

    def test_non_empty(self):
        text = format_kb_for_prompt()
        assert len(text) > 1000

    def test_cached(self):
        """多次调用返回同一对象（缓存生效）."""
        t1 = format_kb_for_prompt()
        t2 = format_kb_for_prompt()
        assert t1 is t2


class TestKBLoading:
    def test_kb_loads_all_entries(self):
        kb = get_morpheme_kb()
        # 444 roots + 82 prefixes + 40 suffixes = 566
        # (header 行不计，实际数据行: roots=444, prefixes=82, suffixes=40)
        assert len(kb) >= 500

    def test_entries_have_correct_categories(self):
        kb = get_morpheme_kb()
        categories = {e.category for e in kb}
        assert categories == {"root", "prefix", "suffix"}


class TestFrozenDataclass:
    def test_immutable(self):
        entry = MorphemeEntry(
            category="root",
            forms=("test",),
            display="TEST",
            description="test desc",
        )
        with pytest.raises(AttributeError):
            entry.category = "prefix"  # type: ignore[misc]
