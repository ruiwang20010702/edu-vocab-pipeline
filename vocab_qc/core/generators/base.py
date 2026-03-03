"""内容生成器基类."""

from typing import Optional

from vocab_qc.core.models import ContentItem


class ContentGenerator:
    """内容生成器协议."""

    dimension: str = ""

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs) -> dict:
        """生成内容.

        Returns:
            {"content": str, "content_cn": Optional[str]}
        """
        raise NotImplementedError
