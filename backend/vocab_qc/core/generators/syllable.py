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

    def _build_user_prompt(self, word: str) -> str:
        return f"Input: {word}"

    def _process_result(self, result: dict, word: str) -> dict:
        if result and result.get("content"):
            return {"content": result["content"], "content_cn": None}
        return {"content": word, "content_cn": None}

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word)
        result = self._call_ai(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result, word)

    async def generate_async(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word)
        result = await self._call_ai_async(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result, word)
