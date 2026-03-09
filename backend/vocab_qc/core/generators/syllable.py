"""音节生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator


class SyllableGenerator(ContentGenerator):
    """音节拆分生成器: AI 模式 + 占位降级."""

    dimension = "syllable"
    prompt_filename = "音节.md"

    def _fallback_prompt(self) -> str:
        return (
            "你是英语语音学专家，按音节拆分英语单词。\n"
            "用中点 · (U+00B7) 作为分隔符。\n"
            '返回 JSON: {"content": "拆分结果"}'
        )

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        session = kwargs.get("session")
        system_prompt = self.get_system_prompt(session)
        user_prompt = f"Input: {word}"

        result = self._call_ai(system_prompt, user_prompt)

        if result and result.get("content"):
            return {"content": result["content"], "content_cn": None}

        # 占位降级: 原样返回
        return {"content": word, "content_cn": None}
