"""内容生成器基类."""

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings

# 项目根目录 → docs/prompts/generation/
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROMPT_DIR = _PROJECT_ROOT / "docs" / "prompts" / "generation"

# 模块级复用的 HTTP 客户端，避免每次请求创建新连接
_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.Client(timeout=60.0)
    return _http_client


def load_prompt_file(filename: str) -> Optional[str]:
    """从 docs/prompts/generation/ 加载 Prompt 文件内容."""
    path = _PROMPT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


@dataclass(frozen=True)
class AiConfig:
    """AI 调用配置，支持 per-dimension 覆盖."""

    system_prompt: str
    model: str
    api_key: str
    base_url: str


class ContentGenerator:
    """内容生成器基类，支持 AI 调用与占位模式."""

    dimension: str = ""
    prompt_filename: str = ""

    def get_ai_config(self, session: Any = None) -> AiConfig:
        """获取完整 AI 配置：Prompt 内容 + 模型/密钥/地址。

        优先级: DB Prompt 配置 → 全局 settings。
        """
        system_prompt = ""
        model = settings.ai_model
        api_key = settings.ai_api_key
        base_url = settings.ai_api_base_url

        # 1. 尝试从 DB 获取 Prompt 及其 AI 配置
        if session:
            try:
                from vocab_qc.core.services.prompt_service import get_active_prompt

                prompt = get_active_prompt(session, "generation", self.dimension)
                if prompt:
                    if prompt.content:
                        system_prompt = prompt.content
                    if prompt.model:
                        model = prompt.model
                    if prompt.ai_api_key:
                        api_key = prompt.ai_api_key
                    if prompt.ai_api_base_url:
                        base_url = prompt.ai_api_base_url
            except Exception:
                logging.getLogger(__name__).warning("从数据库获取 Prompt 配置失败", exc_info=True)

        # 2. Prompt 文本 fallback: 文件 → 硬编码
        if not system_prompt:
            if self.prompt_filename:
                file_prompt = load_prompt_file(self.prompt_filename)
                if file_prompt:
                    system_prompt = file_prompt
            if not system_prompt:
                system_prompt = self._fallback_prompt()

        return AiConfig(
            system_prompt=system_prompt,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    def _fallback_prompt(self) -> str:
        """硬编码兜底 Prompt，子类可覆盖."""
        return ""

    def resolve_ai_config(self, session: Any = None, _preloaded_config: Optional["AiConfig"] = None, **kwargs: Any) -> "AiConfig":
        """获取 AI 配置：优先使用预加载配置（并发安全），否则从 DB 读取。"""
        if _preloaded_config is not None:
            return _preloaded_config
        return self.get_ai_config(session)

    def generate(self, word: str, meaning: Optional[str] = None, pos: Optional[str] = None, session: Any = None, _preloaded_config: Optional["AiConfig"] = None, **kwargs: Any) -> dict:
        """生成内容.

        Returns:
            {"content": str, "content_cn": Optional[str]}
            助记类型还会返回 {"valid": bool, "formula": str, "chant": str, "script": str}
        """
        raise NotImplementedError

    def _call_ai(self, system_prompt: str, user_prompt: str, model: Optional[str] = None,
                 api_key: Optional[str] = None, base_url: Optional[str] = None) -> dict[str, Any]:
        """同步调用 AI API，返回 JSON 结果.

        支持 per-call 覆盖 model/api_key/base_url。
        无 API 配置时返回空 dict，由子类降级到占位。
        """
        actual_key = api_key or settings.ai_api_key
        actual_url = base_url or settings.ai_api_base_url
        actual_model = model or settings.ai_model

        if not actual_key or not actual_url:
            return {}

        last_error = None
        for attempt in range(settings.ai_max_retries):
            try:
                return self._do_request(actual_url, actual_key, actual_model, system_prompt, user_prompt)
            except Exception as e:
                last_error = e
                if attempt < settings.ai_max_retries - 1:
                    time.sleep(2**attempt)

        raise RuntimeError(f"AI 生成失败（{settings.ai_max_retries}次重试后）: {last_error}")

    @staticmethod
    def _validate_url(base_url: str) -> None:
        """校验 AI API URL 防止 SSRF（委托给统一安全模块）。"""
        from vocab_qc.core.security import validate_ai_url

        validate_ai_url(base_url)

    def _do_request(
        self, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        self._validate_url(base_url)
        client = _get_http_client()
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
