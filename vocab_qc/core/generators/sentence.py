"""例句生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator

SYSTEM_PROMPT = """\
你是英语教学专家，为中小学生生成英语例句。

要求：
1. 例句必须准确体现指定义项的含义
2. 句子结构以 主谓宾 或 主系表 为主
3. 长度 8-15 个词，不超过 20 个词
4. 用词不超过初中大纲，连接词限 and/but/so/because
5. 不使用非谓语动词、虚拟语气、倒装句、独立主格
6. 同时提供准确的中文翻译

返回 JSON 格式：
{"content": "英文例句", "content_cn": "中文翻译"}
"""


class SentenceGenerator(ContentGenerator):
    """例句生成器: AI 模式 + 占位降级."""

    dimension = "sentence"

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        user_prompt = f"单词: {word}\n词性: {pos or '未知'}\n释义: {meaning or '未知'}"

        result = self._call_ai(SYSTEM_PROMPT, user_prompt)

        if result and result.get("content"):
            return {
                "content": result["content"],
                "content_cn": result.get("content_cn"),
            }

        # 占位降级
        return {"content": f"This is a {word}.", "content_cn": f"这是一个{word}。"}
