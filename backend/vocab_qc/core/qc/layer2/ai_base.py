"""AI 调用封装: 重试 + 并发控制."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings
from vocab_qc.core.generators.base import (
    AiRequestError,
    build_ai_request,
    parse_ai_response,
    parse_async_submit_response,
    poll_gateway_task_async,
)
from vocab_qc.core.qc.base import RuleResult

logger = logging.getLogger(__name__)


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
                logger.warning(
                    "AI 质检调用失败 [%s] attempt=%d/%d: %s",
                    self.model, attempt + 1, self.max_retries, e,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(f"AI API 调用失败（{self.max_retries}次重试后）: {last_error}")

    async def _call_api(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.api_key or not self.base_url:
            logger.warning("AI API 未配置，占位模式跳过校验")
            return {"passed": True, "detail": "占位模式 - 未配置 AI API"}

        url, headers, body = build_ai_request(
            self.base_url, self.api_key, self.model,
            system_prompt, user_prompt, temperature=0,
        )
        client = self._get_http_client()
        t0 = time.monotonic()
        try:
            response = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("timeout", elapsed_ms=elapsed, detail=str(e)) from e
        except httpx.ConnectError as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("connect_error", elapsed_ms=elapsed, detail=str(e)) from e

        elapsed = int((time.monotonic() - t0) * 1000)
        if response.status_code >= 400:
            raise AiRequestError(
                "http_error",
                status_code=response.status_code,
                response_body=response.text[:500],
                elapsed_ms=elapsed,
            )
        data = response.json()

        # Gateway 异步模式：提交 → 轮询
        if settings.ai_gateway_mode and settings.ai_gateway_async:
            task_no = parse_async_submit_response(data)
            logger.info("Gateway async 质检提交 task_no=%s model=%s", task_no, self.model)
            data = await poll_gateway_task_async(client, self.base_url, task_no, body)

        content = parse_ai_response(data)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise AiRequestError(
                "parse_error", elapsed_ms=elapsed,
                response_body=content[:500], detail=str(e),
            ) from e


class AiRuleChecker:
    """Layer 2 AI 规则检查器基类."""

    rule_id: str = ""
    dimension: str = ""
    description: str = ""
    system_prompt: str = ""

    def build_user_prompt(self, content: str, word: str, meaning: Optional[str] = None, **kwargs) -> str:
        raise NotImplementedError

    async def check(
        self, client: AiClient, content: str, word: str,
        meaning: Optional[str] = None, **kwargs,
    ) -> RuleResult:
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
