"""语块生成器."""

from typing import Optional

from vocab_qc.core.generators.base import ContentGenerator


class ChunkGenerator(ContentGenerator):
    """语块生成器（双模式：规则引擎 + AI）."""

    dimension = "chunk"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs) -> dict:
        """生成语块.

        实际生产中由 AI 模型生成，此处提供框架。
        """
        # 占位实现
        return {"content": f"{word} + ...", "content_cn": None}
