"""内容生成器基类."""

import json
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings


class ContentGenerator:
    """内容生成器基类，支持 AI 调用与占位模式."""

    dimension: str = ""

    def get_custom_prompt(self, session: Any) -> Optional[str]:
        """从数据库获取自定义 Prompt 模板（如有）."""
        try:
            from vocab_qc.core.services.prompt_service import get_active_prompt

            prompt = get_active_prompt(session, "generation", self.dimension)
            if prompt and prompt.content:
                return prompt.content
        except Exception:
            pass
        return None

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, **kwargs: Any) -> dict:
        """生成内容.

        Returns:
            {"content": str, "content_cn": Optional[str]}
        """
        raise NotImplementedError

    def _call_ai(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> dict[str, Any]:
        """同步调用 AI API，返回 JSON 结果.

        无 API 配置时返回 None，由子类降级到占位。
        """
        api_key = settings.ai_api_key
        base_url = settings.ai_api_base_url
        ai_model = model or settings.ai_model

        if not api_key or not base_url:
            return {}

        last_error = None
        for attempt in range(settings.ai_max_retries):
            try:
                return self._do_request(base_url, api_key, ai_model, system_prompt, user_prompt)
            except Exception as e:
                last_error = e
                if attempt < settings.ai_max_retries - 1:
                    import time

                    time.sleep(2**attempt)

        raise RuntimeError(f"AI 生成失败（{settings.ai_max_retries}次重试后）: {last_error}")

    def _do_request(
        self, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.7,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
