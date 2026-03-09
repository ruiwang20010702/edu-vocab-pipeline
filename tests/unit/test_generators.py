"""内容生成器单元测试."""

from unittest.mock import patch

from vocab_qc.core.generators.chunk import ChunkGenerator
from vocab_qc.core.generators.mnemonic import MnemonicGenerator
from vocab_qc.core.generators.sentence import SentenceGenerator


class TestChunkGenerator:
    def test_fallback_without_api(self):
        """无 API 配置时应返回占位内容."""
        gen = ChunkGenerator()
        result = gen.generate("apple", meaning="苹果", pos="n.")
        assert "apple" in result["content"]
        assert isinstance(result["content"], str)

    def test_ai_mode(self):
        """AI 模式应返回 AI 生成的内容."""
        gen = ChunkGenerator()
        with patch.object(gen, "_call_ai", return_value={"content": "eat an apple"}):
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


class TestMnemonicGenerator:
    def test_fallback_without_api(self):
        gen = MnemonicGenerator()
        result = gen.generate("apple")
        assert "[词中词]" in result["content"]
        assert result["content_cn"] is None

    def test_ai_mode(self):
        gen = MnemonicGenerator()
        ai_content = "[词中词] app + le\n[核心公式] apple = app(应用) + le\n[助记口诀] 手机应用画苹果\n[老师话术] 把apple拆成app和le"
        with patch.object(gen, "_call_ai", return_value={"content": ai_content}):
            result = gen.generate("apple")
        assert "[词中词]" in result["content"]
        assert "app" in result["content"]
