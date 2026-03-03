"""助记生成器."""

from typing import Optional

from vocab_qc.core.generators.base import ContentGenerator


class MnemonicGenerator(ContentGenerator):
    """助记生成器（双模式：规则引擎 + AI）."""

    dimension = "mnemonic"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs) -> dict:
        """生成助记内容."""
        return {"content": f"[词中词]\n[核心公式] {word} = ...\n[助记口诀] ...\n[老师话术] ...", "content_cn": None}
