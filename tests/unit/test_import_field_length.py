"""导入字段长度校验测试."""

from vocab_qc.core.services.import_service import (
    _MAX_DEFINITION_LEN,
    _MAX_IPA_LEN,
    _MAX_POS_LEN,
    _MAX_SOURCE_LEN,
    _MAX_WORD_LEN,
    _parse_csv_text,
    _truncate_field,
)


class TestTruncateField:
    def test_normal_length_unchanged(self):
        assert _truncate_field("hello", 100, "test", "word") == "hello"

    def test_exact_max_unchanged(self):
        s = "a" * 100
        assert _truncate_field(s, 100, "test", "word") == s

    def test_over_max_truncated(self):
        s = "a" * 150
        result = _truncate_field(s, 100, "test", "word")
        assert len(result) == 100


class TestCsvFieldLength:
    def test_long_word_skipped(self):
        """超长单词应被跳过。"""
        long_word = "a" * (_MAX_WORD_LEN + 1)
        csv_text = f"word,pos,definition\n{long_word},n.,test\napple,n.,苹果"
        entries = _parse_csv_text(csv_text)
        words = [e["word"] for e in entries]
        assert long_word not in words
        assert "apple" in words

    def test_long_pos_truncated(self):
        """超长词性应被截断。"""
        long_pos = "x" * (_MAX_POS_LEN + 10)
        csv_text = f"word,pos,definition\napple,{long_pos},苹果"
        entries = _parse_csv_text(csv_text)
        assert len(entries) == 1
        assert len(entries[0]["meanings"][0]["pos"]) == _MAX_POS_LEN

    def test_long_definition_truncated(self):
        long_def = "字" * (_MAX_DEFINITION_LEN + 10)
        csv_text = f"word,pos,definition\napple,n.,{long_def}"
        entries = _parse_csv_text(csv_text)
        assert len(entries[0]["meanings"][0]["definition"]) == _MAX_DEFINITION_LEN

    def test_long_source_truncated(self):
        long_src = "s" * (_MAX_SOURCE_LEN + 10)
        csv_text = f"word,pos,definition,source\napple,n.,苹果,{long_src}"
        entries = _parse_csv_text(csv_text)
        assert len(entries[0]["meanings"][0]["sources"][0]) == _MAX_SOURCE_LEN

    def test_long_ipa_truncated(self):
        long_ipa = "/" + "x" * (_MAX_IPA_LEN + 10)
        csv_text = f"word,pos,definition,ipa\napple,n.,苹果,{long_ipa}"
        entries = _parse_csv_text(csv_text)
        assert len(entries[0]["ipa"]) == _MAX_IPA_LEN

    def test_normal_data_unaffected(self):
        csv_text = "word,pos,definition,source,ipa\napple,n.,苹果,人教七上,/ˈæp.əl/"
        entries = _parse_csv_text(csv_text)
        assert entries[0]["word"] == "apple"
        assert entries[0]["meanings"][0]["pos"] == "n."
        assert entries[0]["meanings"][0]["definition"] == "苹果"
