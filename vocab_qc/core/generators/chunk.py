"""语块生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator

SYSTEM_PROMPT = """\
你是英语教学专家，为中小学生生成词汇语块（chunk）。

要求：
1. 语块必须是该词在指定义项下的高频搭配（动宾、形名、介宾等）
2. 语块长度 2-5 个词
3. 用词不超过初中大纲
4. 不得包含生僻词或专业术语

返回 JSON 格式：
{"content": "生成的语块"}
"""


class ChunkGenerator(ContentGenerator):
    """语块生成器: AI 模式 + 占位降级."""

    dimension = "chunk"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        user_prompt = f"单词: {word}\n词性: {pos or '未知'}\n释义: {meaning or '未知'}"

        result = self._call_ai(SYSTEM_PROMPT, user_prompt)

        if result and result.get("content"):
            return {"content": result["content"], "content_cn": result.get("content_cn")}

        # 占位降级
        return {"content": f"{word} + ...", "content_cn": None}
