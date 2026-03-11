"""语块生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator


class ChunkGenerator(ContentGenerator):
    """语块生成器: AI 模式 + 占位降级."""

    dimension = "chunk"
    prompt_filename = "语块.md"

    def _fallback_prompt(self) -> str:
        return (
            "你是英语教学专家，为中小学生生成词汇语块。\n"
            "返回 JSON: {\"content\": \"英文语块\", \"content_cn\": \"中文翻译\"}"
        )

    def _build_user_prompt(self, word: str, pos: Optional[str], meaning: Optional[str]) -> str:
        return f"Word: {word} | POS: {pos or '未知'} | Meaning: {meaning or '未知'}"

    def _process_result(self, result: dict, word: str) -> dict:
        if result and result.get("content"):
            return {"content": result["content"], "content_cn": result.get("content_cn")}
        return {"content": f"{word} + ...", "content_cn": None}

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word, pos, meaning)
        result = self._call_ai(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result, word)

    async def generate_async(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        ai_config = self.resolve_ai_config(**kwargs)
        user_prompt = self._build_user_prompt(word, pos, meaning)
        result = await self._call_ai_async(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )
        return self._process_result(result, word)
