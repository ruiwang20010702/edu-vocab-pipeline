"""AI 调用封装: 重试 + 并发控制."""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings

logger = logging.getLogger(__name__)
from vocab_qc.core.qc.base import RuleResult


@dataclass(frozen=True)
class AiCheckResult:
    """AI 校验结果."""

    rule_id: str
    passed: bool
    detail: Optional[str] = None
    model: Optional[str] = None


class AiClient:
    """AI API 客户端封装."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_concurrency: int = 20,
        max_retries: int = 3,
    ):
        self.api_key = api_key if api_key is not None else settings.ai_api_key
        self.base_url = base_url if base_url is not None else settings.ai_api_base_url
        self.model = model if model is not None else settings.ai_model
        self.max_retries = max_retries
        self._max_concurrency = max_concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_loop: asyncio.AbstractEventLoop | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._http_client_loop: asyncio.AbstractEventLoop | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """延迟创建 AsyncClient，事件循环变化时自动重建。"""
        loop = asyncio.get_running_loop()
        if self._http_client is None or self._http_client_loop is not loop:
            self._http_client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(
                    max_connections=self._max_concurrency,
                    max_keepalive_connections=self._max_concurrency,
                ),
            )
            self._http_client_loop = loop
        return self._http_client

    def _get_semaphore(self) -> asyncio.Semaphore:
        """延迟创建 Semaphore，事件循环变化时自动重建。"""
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
            self._semaphore_loop = loop
        return self._semaphore

    async def check(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """发送 AI 校验请求，返回 JSON 结果."""
        async with self._get_semaphore():
            return await self._call_with_retry(system_prompt, user_prompt)

    async def _call_with_retry(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await self._call_api(system_prompt, user_prompt)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(f"AI API 调用失败（{self.max_retries}次重试后）: {last_error}")

    async def _call_api(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.api_key or not self.base_url:
            logger.warning("AI API 未配置，占位模式跳过校验")
            return {"passed": True, "detail": "占位模式 - 未配置 AI API"}

        response = await self._get_http_client().post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


class AiRuleChecker:
    """Layer 2 AI 规则检查器基类."""

    rule_id: str = ""
    dimension: str = ""
    description: str = ""
    system_prompt: str = ""

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError

    async def check(self, client: AiClient, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> RuleResult:
        user_prompt = self.build_user_prompt(content, word, meaning, **kwargs)
        try:
            result = await client.check(self.system_prompt, user_prompt)
            return RuleResult(
                rule_id=self.rule_id,
                passed=result.get("passed", False),
                detail=result.get("detail"),
            )
        except Exception as e:
            return RuleResult(rule_id=self.rule_id, passed=False, detail=f"AI 调用失败: {e}")
