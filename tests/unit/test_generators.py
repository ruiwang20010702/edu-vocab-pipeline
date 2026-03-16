"""内容生成器单元测试."""

import json
from unittest.mock import patch

from vocab_qc.core.generators.chunk import ChunkGenerator
from vocab_qc.core.generators.mnemonic import (
    ExamAppMnemonicGenerator,
    RootAffixMnemonicGenerator,
    SoundMeaningMnemonicGenerator,
    WordInWordMnemonicGenerator,
)
from vocab_qc.core.generators.sentence import SentenceGenerator
from vocab_qc.core.generators.syllable import SyllableGenerator


class TestChunkGenerator:
    def test_fallback_without_api(self):
        """无 API 配置时应返回占位内容."""
        gen = ChunkGenerator()
        with patch.object(gen, "_call_ai", return_value={}):
            result = gen.generate("apple", meaning="苹果", pos="n.")
        assert "apple" in result["content"]
        assert isinstance(result["content"], str)

    def test_ai_mode(self):
        """AI 模式应返回 AI 生成的内容."""
        gen = ChunkGenerator()
        with patch.object(gen, "_call_ai", return_value={"content": "eat an apple", "content_cn": "吃苹果"}):
            result = gen.generate("apple", meaning="苹果", pos="n.")
        assert result["content"] == "eat an apple"

    def test_ai_empty_fallback(self):
        """AI 返回空时应降级到占位."""
        gen = ChunkGenerator()
        with patch.object(gen, "_call_ai", return_value={}):
            result = gen.generate("apple", meaning="苹果", pos="n.")
        assert "apple" in result["content"]


class TestSentenceGenerator:
    def test_fallback_without_api(self):
        gen = SentenceGenerator()
        with patch.object(gen, "_call_ai", return_value={}):
            result = gen.generate("book", meaning="书", pos="n.")
        assert "book" in result["content"]
        assert result["content_cn"] is not None

    def test_ai_mode(self):
        gen = SentenceGenerator()
        ai_resp = {"content": "I read a book every day.", "content_cn": "我每天读一本书。"}
        with patch.object(gen, "_call_ai", return_value=ai_resp):
            result = gen.generate("book", meaning="书", pos="n.")
        assert result["content"] == "I read a book every day."
        assert result["content_cn"] == "我每天读一本书。"


class TestSyllableGenerator:
    def test_fallback_without_api(self):
        gen = SyllableGenerator()
        with patch.object(gen, "_call_ai", return_value={}):
            result = gen.generate("apple")
        assert result["content"] == "apple"

    def test_ai_mode(self):
        gen = SyllableGenerator()
        with patch.object(gen, "_call_ai", return_value={"content": "ap·ple"}):
            result = gen.generate("apple")
        assert result["content"] == "ap·ple"


class TestRootAffixMnemonicGenerator:
    def test_fallback_without_api(self):
        gen = RootAffixMnemonicGenerator()
        with patch.object(gen, "_call_ai", return_value={}):
            result = gen.generate("invisible", meaning="看不见的", pos="adj.")
        assert result["valid"] is False
        assert result["content"] is None

    def test_ai_valid(self):
        gen = RootAffixMnemonicGenerator()
        ai_resp = {
            "valid": True,
            "formula": "in(不) + vis(看) + ible(能…的)",
            "chant": "不能被看见",
            "script": "XX同学，来看这个词...",
        }
        with patch.object(gen, "_call_ai", return_value=ai_resp):
            result = gen.generate("invisible", meaning="看不见的", pos="adj.")
        assert result["valid"] is True
        # content 为 JSON 格式
        parsed = json.loads(result["content"])
        assert parsed["formula"] == ai_resp["formula"]
        assert parsed["chant"] == ai_resp["chant"]
        assert parsed["script"] == ai_resp["script"]
        assert result["formula"] == ai_resp["formula"]

    def test_ai_invalid(self):
        gen = RootAffixMnemonicGenerator()
        with patch.object(gen, "_call_ai", return_value={"valid": False}):
            result = gen.generate("dog", meaning="狗", pos="n.")
        assert result["valid"] is False
        assert result["content"] is None


class TestProcessResultEdgeCases:
    def test_none_input(self):
        from vocab_qc.core.generators.mnemonic import _MnemonicBase
        result = _MnemonicBase._process_result(None)
        assert result["valid"] is False

    def test_valid_string_false(self):
        from vocab_qc.core.generators.mnemonic import _MnemonicBase
        result = _MnemonicBase._process_result({"valid": "false"})
        assert result["valid"] is False

    def test_valid_zero(self):
        from vocab_qc.core.generators.mnemonic import _MnemonicBase
        result = _MnemonicBase._process_result({"valid": 0})
        assert result["valid"] is False

    def test_missing_chant_field(self):
        from vocab_qc.core.generators.mnemonic import _MnemonicBase
        result = _MnemonicBase._process_result(
            {"valid": True, "formula": "a+b", "script": "..."}
        )
        assert result["valid"] is True
        parsed = json.loads(result["content"])
        assert parsed["chant"] == ""

    def test_ai_valid_string_false_via_generator(self):
        """AI 返回字符串 'false' 时应视为无效."""
        gen = RootAffixMnemonicGenerator()
        with patch.object(gen, "_call_ai", return_value={"valid": "false"}):
            result = gen.generate("dog", meaning="狗", pos="n.")
        assert result["valid"] is False


class TestRootAffixSystemPrompt:
    def test_system_prompt_contains_kb(self):
        """词根词缀助记的 system prompt 应包含知识库."""
        gen = RootAffixMnemonicGenerator()
        config = gen.get_ai_config()
        assert "词根词缀知识库" in config.system_prompt
        assert "## 前缀" in config.system_prompt
        assert "## 词根" in config.system_prompt
        assert "## 后缀" in config.system_prompt

    def test_system_prompt_preserves_original(self):
        """注入知识库后仍保留原始 system prompt 内容."""
        gen = RootAffixMnemonicGenerator()
        original = super(RootAffixMnemonicGenerator, gen).get_ai_config()
        enriched = gen.get_ai_config()
        assert enriched.system_prompt.startswith(original.system_prompt)


class TestWordInWordMnemonicGenerator:
    def test_dimension(self):
        gen = WordInWordMnemonicGenerator()
        assert gen.dimension == "mnemonic_word_in_word"


class TestSoundMeaningMnemonicGenerator:
    def test_dimension(self):
        gen = SoundMeaningMnemonicGenerator()
        assert gen.dimension == "mnemonic_sound_meaning"


class TestExamAppMnemonicGenerator:
    def test_dimension(self):
        gen = ExamAppMnemonicGenerator()
        assert gen.dimension == "mnemonic_exam_app"
