"""例句生成器."""

from typing import Optional

from vocab_qc.core.generators.base import ContentGenerator


class SentenceGenerator(ContentGenerator):
    """例句生成器（双模式：规则引擎 + AI）."""

    dimension = "sentence"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs) -> dict:
        """生成例句 + 中文翻译."""
        return {"content": f"This is a {word}.", "content_cn": f"这是一个{word}。"}
