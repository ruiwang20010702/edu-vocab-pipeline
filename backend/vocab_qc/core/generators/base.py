"""内容生成器基类."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings

# 项目根目录 → docs/prompts/generation/
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROMPT_DIR = _PROJECT_ROOT / "docs" / "prompts" / "generation"


def load_prompt_file(filename: str) -> Optional[str]:
    """从 docs/prompts/generation/ 加载 Prompt 文件内容."""
    path = _PROMPT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


class ContentGenerator:
    """内容生成器基类，支持 AI 调用与占位模式."""

    dimension: str = ""
    prompt_filename: str = ""

    def get_custom_prompt(self, session: Any) -> Optional[str]:
        """从数据库获取自定义 Prompt 模板（如有）."""
        try:
            from vocab_qc.core.services.prompt_service import get_active_prompt

            prompt = get_active_prompt(session, "generation", self.dimension)
            if prompt and prompt.content:
                return prompt.content
        except Exception:
            logging.getLogger(__name__).warning("从数据库获取自定义 Prompt 失败", exc_info=True)
        return None

    def get_system_prompt(self, session: Any = None) -> str:
        """获取系统 Prompt：DB 优先 → 文件 → 硬编码兜底."""
        if session:
            db_prompt = self.get_custom_prompt(session)
            if db_prompt:
                return db_prompt

        if self.prompt_filename:
            file_prompt = load_prompt_file(self.prompt_filename)
            if file_prompt:
                return file_prompt

        return self._fallback_prompt()

    def _fallback_prompt(self) -> str:
        """硬编码兜底 Prompt，子类可覆盖."""
        return ""

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, session: Any = None, **kwargs: Any) -> dict:
        """生成内容.

        Returns:
            {"content": str, "content_cn": Optional[str]}
            助记类型还会返回 {"valid": bool, "formula": str, "chant": str, "script": str}
        """
        raise NotImplementedError

    def _call_ai(self, system_prompt: str, user_prompt: str, model: Optional[str] = None) -> dict[str, Any]:
        """同步调用 AI API，返回 JSON 结果.

        无 API 配置时返回空 dict，由子类降级到占位。
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
                    time.sleep(2**attempt)

        raise RuntimeError(f"AI 生成失败（{settings.ai_max_retries}次重试后）: {last_error}")

    @staticmethod
    def _validate_url(base_url: str) -> None:
        """校验 AI API URL 防止 SSRF。"""
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"AI API base_url scheme 不合法: {parsed.scheme}")
        hostname = parsed.hostname or ""
        _BLOCKED_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254")
        _BLOCKED_PREFIXES = ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                             "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                             "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")
        if hostname in _BLOCKED_HOSTS or any(hostname.startswith(p) for p in _BLOCKED_PREFIXES):
            from vocab_qc.core.config import settings as _s
            if _s.env == "production":
                raise ValueError("生产环境禁止使用内网 AI API 地址")

    def _do_request(
        self, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        self._validate_url(base_url)
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
