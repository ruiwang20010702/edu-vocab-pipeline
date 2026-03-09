"""例句生成器."""

from typing import Any, Optional

from vocab_qc.core.generators.base import ContentGenerator


class SentenceGenerator(ContentGenerator):
    """例句生成器: AI 模式 + 占位降级."""

    dimension = "sentence"
    prompt_filename = "例句.md"

    def _fallback_prompt(self) -> str:
        return (
            "你是英语教学专家，为中小学生生成英语例句。\n"
            "返回 JSON: {\"content\": \"英文例句\", \"content_cn\": \"中文翻译\"}"
        )

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        session = kwargs.get("session")
        ai_config = self.get_ai_config(session)
        user_prompt = f"Word: {word} | POS: {pos or '未知'} | Meaning: {meaning or '未知'}"

        result = self._call_ai(
            ai_config.system_prompt, user_prompt,
            model=ai_config.model, api_key=ai_config.api_key, base_url=ai_config.base_url,
        )

        if result and result.get("content"):
            return {"content": result["content"], "content_cn": result.get("content_cn")}

        # 占位降级
        return {"content": f"This is a {word}.", "content_cn": f"这是一个{word}。"}
