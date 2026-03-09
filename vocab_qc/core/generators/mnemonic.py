"""助记生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator

SYSTEM_PROMPT = """\
你是英语教学专家，为中小学生生成单词助记法。

助记法面向拼写和发音，与具体义项无关。格式要求：

[词中词] 拆解单词中包含的已知小词
[核心公式] word = 拆解部分 的组合公式
[助记口诀] 一句押韵或有画面感的口诀
[老师话术] 用口语化的方式讲解助记过程，50 字以内

返回 JSON 格式：
{"content": "完整的助记内容，包含上述四个部分"}
"""


class MnemonicGenerator(ContentGenerator):
    """助记生成器: AI 模式 + 占位降级."""

    dimension = "mnemonic"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        user_prompt = f"单词: {word}"

        result = self._call_ai(SYSTEM_PROMPT, user_prompt)

        if result and result.get("content"):
            return {"content": result["content"], "content_cn": None}

        # 占位降级
        return {
            "content": f"[词中词]\n[核心公式] {word} = ...\n[助记口诀] ...\n[老师话术] ...",
            "content_cn": None,
        }
