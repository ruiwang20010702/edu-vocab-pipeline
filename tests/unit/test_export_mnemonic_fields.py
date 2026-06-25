"""_parse_mnemonic_fields 单元测试: 验证 exam_sentence 字段的导出兼容性."""

import json

from vocab_qc.core.services.export_service import _parse_mnemonic_fields

_EMPTY = {
    "formula": "", "chant": "",
    "extension_words": "",
    "exam_sentence": "", "exam_sentence_translation": "",
    "script": "",
}


class TestParseMnemonicFields:
    def test_full_json_with_exam_sentence_and_translation(self):
        content = json.dumps(
            {
                "formula": "consistent + with",
                "chant": "锁with",
                "exam_sentence": "His words are consistent with his actions every single day.",
                "exam_sentence_translation": "他的言行每天都保持一致。",
                "script": "话术内容",
            },
            ensure_ascii=False,
        )
        result = _parse_mnemonic_fields(content)
        assert result["formula"] == "consistent + with"
        assert result["chant"] == "锁with"
        assert result["exam_sentence"] == "His words are consistent with his actions every single day."
        assert result["exam_sentence_translation"] == "他的言行每天都保持一致。"
        assert result["script"] == "话术内容"

    def test_legacy_3key_json_defaults_exam_sentence_empty(self):
        """旧数据不含 exam_sentence/translation 字段时，导出应填空串."""
        content = json.dumps({"formula": "f", "chant": "c", "script": "s"}, ensure_ascii=False)
        result = _parse_mnemonic_fields(content)
        assert result["formula"] == "f"
        assert result["chant"] == "c"
        assert result["script"] == "s"
        assert result["exam_sentence"] == ""
        assert result["exam_sentence_translation"] == ""

    def test_legacy_4key_json_with_exam_sentence_only(self):
        """仅含 exam_sentence 无 translation 的过渡期数据：translation 默认空，例句保留."""
        content = json.dumps(
            {
                "formula": "f", "chant": "c",
                "exam_sentence": "He is consistent with the plan in every meeting always.",
                "script": "s",
            },
            ensure_ascii=False,
        )
        result = _parse_mnemonic_fields(content)
        assert result["exam_sentence"] == "He is consistent with the plan in every meeting always."
        assert result["exam_sentence_translation"] == ""

    def test_empty_content_returns_all_empty(self):
        result = _parse_mnemonic_fields("")
        assert result == _EMPTY

    def test_invalid_json_returns_all_empty(self):
        result = _parse_mnemonic_fields("not json at all")
        assert result == _EMPTY

    def test_legacy_tag_format_no_exam_sentence(self):
        """老的 [核心公式] / [助记口诀] / [老师话术] 标签格式仍能解析，例句和释义默认空."""
        content = "[核心公式] a + b\n[助记口诀] 记住\n[老师话术] 话术内容"
        result = _parse_mnemonic_fields(content)
        assert result["formula"] == "a + b"
        assert result["chant"] == "记住"
        assert result["script"] == "话术内容"
        assert result["exam_sentence"] == ""
        assert result["exam_sentence_translation"] == ""

    def test_partial_json_missing_keys_default_empty(self):
        """JSON 仅含 formula 时其他字段默认空串."""
        content = json.dumps({"formula": "only formula"}, ensure_ascii=False)
        result = _parse_mnemonic_fields(content)
        assert result["formula"] == "only formula"
        assert result["chant"] == ""
        assert result["extension_words"] == ""
        assert result["exam_sentence"] == ""
        assert result["exam_sentence_translation"] == ""
        assert result["script"] == ""

    def test_root_affix_json_with_extension_words(self):
        """词根词缀维度新版 JSON 含 extension_words 字段时正常解析."""
        content = json.dumps(
            {
                "formula": "in(不) + vis(看) + ible(能…的，形容词后缀)",
                "chant": "不能被看见。",
                "extension_words": "vision (视力); visual (视觉的); visit (去看望)",
                "script": "话术内容",
            },
            ensure_ascii=False,
        )
        result = _parse_mnemonic_fields(content)
        assert result["formula"] == "in(不) + vis(看) + ible(能…的，形容词后缀)"
        assert result["chant"] == "不能被看见。"
        assert result["extension_words"] == "vision (视力); visual (视觉的); visit (去看望)"
        assert result["script"] == "话术内容"
        # 不应混入 exam_app 维度字段
        assert result["exam_sentence"] == ""
        assert result["exam_sentence_translation"] == ""

    def test_legacy_3key_json_defaults_extension_words_empty(self):
        """老的词根词缀 3-key JSON（无 extension_words）解析后该字段默认空串，不报错."""
        content = json.dumps(
            {"formula": "f", "chant": "c", "script": "s"},
            ensure_ascii=False,
        )
        result = _parse_mnemonic_fields(content)
        assert result["extension_words"] == ""
        assert result["formula"] == "f"
