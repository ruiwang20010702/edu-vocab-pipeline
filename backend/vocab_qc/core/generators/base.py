"""内容生成器基类."""

import asyncio
import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from vocab_qc.core.config import settings
from vocab_qc.core.generators import _find_project_root

logger = logging.getLogger(__name__)


class AiRequestError(Exception):
    """AI 请求错误，携带完整诊断信息。"""

    def __init__(
        self,
        error_type: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
        elapsed_ms: int = 0,
        detail: str = "",
        task_no: str = "",
    ):
        self.error_type = error_type  # timeout / connect_error / http_error / parse_error / task_*
        self.status_code = status_code
        self.response_body = response_body
        self.elapsed_ms = elapsed_ms
        self.detail = detail
        self.task_no = task_no
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [self.error_type]
        if self.status_code:
            parts.append(f"HTTP {self.status_code}")
        if self.elapsed_ms:
            parts.append(f"{self.elapsed_ms}ms")
        if self.response_body:
            parts.append(self.response_body[:200])
        elif self.detail:
            parts.append(self.detail[:200])
        return " | ".join(parts)


def build_ai_request(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """构造 AI 请求参数（模块级公共函数，生成 + 质检共用）。"""
    import uuid

    safe_prompt = ContentGenerator._ensure_json_hint(system_prompt)

    if settings.ai_gateway_mode:
        headers = {"Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": model,
            "provider": ContentGenerator._resolve_gateway_provider(model),
            "api_key": api_key,
            "biz_type": settings.ai_gateway_biz_type,
            "biz_id": str(uuid.uuid4()),
            "stream": False,
            "async": bool(settings.ai_gateway_async),
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": safe_prompt}]},
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }
    else:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": safe_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
        }

    url = f"{base_url}/chat/completions"
    return url, headers, body


def _strip_markdown_fences(text: str) -> str:
    """剥掉 AI 返回的 markdown 代码块标记（```json ... ```）。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        # 去掉首行 ```json 或 ```
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        # 去掉末尾 ```
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    return stripped


def parse_ai_response(data: dict[str, Any]) -> str:
    """从响应中提取 content，自动适配 gateway 包裹格式（模块级公共函数）。"""
    if "res" in data and "choices" not in data:
        inner = data["res"]
        if inner is None:
            raise AiRequestError(
                "parse_error",
                detail=f"Gateway 返回 res=null (code={data.get('code')})",
                response_body=str(data)[:500],
            )
        data = inner
    choices = data.get("choices")
    if not choices:
        raise AiRequestError(
            "parse_error",
            detail="响应缺少 choices 字段",
            response_body=str(data)[:500],
        )
    return choices[0]["message"]["content"]


def parse_async_submit_response(data: dict[str, Any]) -> str:
    """解析 Gateway 异步提交响应，返回 task_no。"""
    code = data.get("code")
    res = data.get("res")
    if code != 10000 or not isinstance(res, str):
        raise AiRequestError(
            "task_submit_failed",
            detail=f"code={code}, res={res!r}",
        )
    return res


def parse_poll_response(data: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str]:
    """解析轮询响应，返回 (status, result_dict_or_None, failed_reason)。"""
    code = data.get("code")
    res = data.get("res")
    if code != 10000 or res is None or not isinstance(res, dict) or "status" not in res:
        raise AiRequestError(
            "task_poll_error",
            detail=f"code={code}, res={res!r}",
        )
    return res["status"], res.get("result"), res.get("failed_reason", "")


def build_poll_body(submit_body: dict[str, Any], task_no: str) -> dict[str, Any]:
    """从提交 body 中提取字段，构造轮询请求 body。"""
    return {
        "provider": submit_body["provider"],
        "model": submit_body["model"],
        "api_key": submit_body["api_key"],
        "biz_type": submit_body["biz_type"],
        "biz_id": submit_body["biz_id"],
        "task_no": task_no,
    }


async def poll_gateway_task_async(
    client: httpx.AsyncClient,
    base_url: str,
    task_no: str,
    submit_body: dict[str, Any],
) -> dict[str, Any]:
    """异步轮询 Gateway 任务直到完成/失败/超时。"""
    poll_url = f"{base_url}/chat/task/result"
    poll_body = build_poll_body(submit_body, task_no)
    deadline = time.monotonic() + settings.ai_gateway_poll_max_wait
    start_time = time.monotonic()
    poll_count = 0

    while True:
        if time.monotonic() > deadline:
            raise AiRequestError(
                "task_timeout",
                detail=f"轮询超时({settings.ai_gateway_poll_max_wait}s), task_no={task_no}",
                task_no=task_no,
            )

        await asyncio.sleep(settings.ai_gateway_poll_interval)
        poll_count += 1

        t0 = time.monotonic()
        try:
            response = await client.post(
                poll_url, headers={"Content-Type": "application/json"}, json=poll_body,
            )
        except httpx.TimeoutException as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("timeout", elapsed_ms=elapsed, detail=str(e), task_no=task_no) from e
        except httpx.ConnectError as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("connect_error", elapsed_ms=elapsed, detail=str(e), task_no=task_no) from e

        if response.status_code >= 400:
            raise AiRequestError(
                "http_error",
                status_code=response.status_code,
                response_body=response.text[:500],
                task_no=task_no,
            )

        status, result, failed_reason = parse_poll_response(response.json())

        logger.debug("轮询 task_no=%s attempt=%d status=%s", task_no, poll_count, status)

        if status == "COMPLETED" and result is not None:
            total_elapsed = int((time.monotonic() - start_time) * 1000)
            logger.info("Gateway 任务完成 task_no=%s polls=%d elapsed=%dms", task_no, poll_count, total_elapsed)
            return result
        elif status == "FAILED":
            raise AiRequestError(
                "task_failed",
                detail=f"task_no={task_no}: {failed_reason}",
                task_no=task_no,
            )
        # PENDING / PROCESSING → 继续轮询


def poll_gateway_task_sync(
    client: httpx.Client,
    base_url: str,
    task_no: str,
    submit_body: dict[str, Any],
) -> dict[str, Any]:
    """同步轮询 Gateway 任务直到完成/失败/超时。"""
    poll_url = f"{base_url}/chat/task/result"
    poll_body = build_poll_body(submit_body, task_no)
    deadline = time.monotonic() + settings.ai_gateway_poll_max_wait
    start_time = time.monotonic()
    poll_count = 0

    while True:
        if time.monotonic() > deadline:
            raise AiRequestError(
                "task_timeout",
                detail=f"轮询超时({settings.ai_gateway_poll_max_wait}s), task_no={task_no}",
                task_no=task_no,
            )

        time.sleep(settings.ai_gateway_poll_interval)
        poll_count += 1

        t0 = time.monotonic()
        try:
            response = client.post(
                poll_url, headers={"Content-Type": "application/json"}, json=poll_body,
            )
        except httpx.TimeoutException as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("timeout", elapsed_ms=elapsed, detail=str(e), task_no=task_no) from e
        except httpx.ConnectError as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            raise AiRequestError("connect_error", elapsed_ms=elapsed, detail=str(e), task_no=task_no) from e

        if response.status_code >= 400:
            raise AiRequestError(
                "http_error",
                status_code=response.status_code,
                response_body=response.text[:500],
                task_no=task_no,
            )

        status, result, failed_reason = parse_poll_response(response.json())

        logger.debug("轮询 task_no=%s attempt=%d status=%s", task_no, poll_count, status)

        if status == "COMPLETED" and result is not None:
            total_elapsed = int((time.monotonic() - start_time) * 1000)
            logger.info("Gateway 任务完成 task_no=%s polls=%d elapsed=%dms", task_no, poll_count, total_elapsed)
            return result
        elif status == "FAILED":
            raise AiRequestError(
                "task_failed",
                detail=f"task_no={task_no}: {failed_reason}",
                task_no=task_no,
            )
        # PENDING / PROCESSING → 继续轮询


# S-M2: Prompt Injection 防护
_INJECTION_RE = re.compile(
    r"(ignore\s+(above|previous|all)|system:|<\|im_|忽略以上|忽略前面)",
    re.IGNORECASE,
)


def sanitize_prompt_input(text: str, max_len: int = 200) -> str:
    """清洗用户输入，防止 prompt injection。"""
    if not text:
        return ""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    cleaned = _INJECTION_RE.sub("", cleaned)
    return cleaned[:max_len].strip()

# 项目根目录 → docs/prompts/generation/
_PROJECT_ROOT = _find_project_root()
_PROMPT_DIR = _PROJECT_ROOT / "docs" / "prompts" / "generation"

# 模块级复用的 HTTP 客户端，避免每次请求创建新连接
_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()

# 异步 HTTP 客户端（按事件循环缓存）
_async_http_client: httpx.AsyncClient | None = None
_async_http_client_loop: asyncio.AbstractEventLoop | None = None


def _no_proxy_mounts_sync() -> dict:
    """ai_use_proxy=False 时返回强制直连的 mounts 参数。"""
    if settings.ai_use_proxy:
        return {}
    return {"mounts": {"all://": httpx.HTTPTransport()}}


def _no_proxy_mounts_async() -> dict:
    """ai_use_proxy=False 时返回强制直连的 mounts 参数（异步版）。"""
    if settings.ai_use_proxy:
        return {}
    return {"mounts": {"all://": httpx.AsyncHTTPTransport()}}


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.Client(timeout=60.0, **_no_proxy_mounts_sync())
    return _http_client


def _get_async_http_client() -> httpx.AsyncClient:
    """获取共享的异步 HTTP 客户端，事件循环变化时重建。"""
    global _async_http_client, _async_http_client_loop
    loop = asyncio.get_running_loop()
    if _async_http_client is None or _async_http_client_loop is not loop:
        old = _async_http_client
        _pool_size = (
            settings.ai_max_concurrency * 2
            if settings.ai_gateway_async
            else settings.ai_max_concurrency
        )
        _async_http_client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(
                max_connections=_pool_size,
                max_keepalive_connections=_pool_size,
            ),
            **_no_proxy_mounts_async(),
        )
        _async_http_client_loop = loop
        # 在当前循环中异步关闭旧客户端
        if old is not None:
            loop.create_task(old.aclose())
    return _async_http_client


async def close_http_clients() -> None:
    """关闭共享的 HTTP 客户端，在应用关闭时调用。"""
    global _http_client, _async_http_client
    if _async_http_client is not None:
        await _async_http_client.aclose()
        _async_http_client = None
    if _http_client is not None:
        loop = asyncio.get_running_loop()
        client = _http_client
        _http_client = None
        await loop.run_in_executor(None, client.close)


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

        密钥和地址始终从环境变量读取（安全），仅 Prompt 文本和模型名称可从 DB 覆盖。
        """
        system_prompt = ""
        model = settings.ai_model
        api_key = settings.ai_api_key
        base_url = settings.ai_api_base_url

        # 从 DB 获取 Prompt 文本和模型名称（不读取密钥）
        if session:
            try:
                from vocab_qc.core.services.prompt_service import get_active_prompt

                prompt = get_active_prompt(session, "generation", self.dimension)
                if prompt:
                    if prompt.content:
                        system_prompt = prompt.content
                    if prompt.model:
                        model = prompt.model
            except Exception:
                logging.getLogger(__name__).warning("从数据库获取 Prompt 配置失败", exc_info=True)

        # Prompt 文本 fallback: 文件 → 硬编码
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

    def resolve_ai_config(
        self,
        session: Any = None,
        _preloaded_config: Optional["AiConfig"] = None,
        **kwargs: Any,
    ) -> "AiConfig":
        """获取 AI 配置：优先使用预加载配置（并发安全），否则从 DB 读取。"""
        if _preloaded_config is not None:
            return _preloaded_config
        return self.get_ai_config(session)

    def generate(
        self,
        word: str,
        meaning: Optional[str] = None,
        pos: Optional[str] = None,
        session: Any = None,
        _preloaded_config: Optional["AiConfig"] = None,
        **kwargs: Any,
    ) -> dict:
        """生成内容.

        Returns:
            {"content": str, "content_cn": Optional[str]}
            助记类型还会返回 {"valid": bool, "formula": str, "chant": str, "script": str}
        """
        raise NotImplementedError

    async def generate_async(
        self,
        word: str,
        meaning: Optional[str] = None,
        pos: Optional[str] = None,
        _preloaded_config: Optional["AiConfig"] = None,
        **kwargs: Any,
    ) -> dict:
        """异步生成内容。默认委托给同步 generate（子类可覆盖用 _call_ai_async）。"""
        return self.generate(
            word=word, meaning=meaning, pos=pos,
            _preloaded_config=_preloaded_config, **kwargs,
        )

    def _call_ai(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> dict[str, Any]:
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
                logger.warning(
                    "AI 调用失败 [%s] attempt=%d/%d: %s",
                    actual_model, attempt + 1, settings.ai_max_retries, e,
                )
                if attempt < settings.ai_max_retries - 1:
                    time.sleep(2**attempt + random.uniform(0, 1))

        raise RuntimeError(f"AI 生成失败（{settings.ai_max_retries}次重试后）: {last_error}")

    async def _call_ai_async(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """异步调用 AI API，使用共享的 httpx.AsyncClient。"""
        actual_key = api_key or settings.ai_api_key
        actual_url = base_url or settings.ai_api_base_url
        actual_model = model or settings.ai_model

        if not actual_key or not actual_url:
            return {}

        self._validate_url(actual_url)

        url, headers, body = self._build_request(actual_url, actual_key, actual_model, system_prompt, user_prompt)
        client = _get_async_http_client()
        last_error = None
        for attempt in range(settings.ai_max_retries):
            t0 = time.monotonic()
            try:
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
                    logger.info("Gateway async 提交成功 task_no=%s model=%s", task_no, actual_model)
                    data = await poll_gateway_task_async(client, actual_url, task_no, body)

                content = _strip_markdown_fences(self._parse_response(data))
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    raise AiRequestError(
                        "parse_error", elapsed_ms=elapsed,
                        response_body=content[:500], detail=str(e),
                    ) from e
            except Exception as e:
                last_error = e
                logger.warning(
                    "AI 调用失败 [%s] attempt=%d/%d: %s",
                    actual_model, attempt + 1, settings.ai_max_retries, e,
                )
                if attempt < settings.ai_max_retries - 1:
                    await asyncio.sleep(2**attempt + random.uniform(0, 1))

        raise RuntimeError(f"AI 生成失败（{settings.ai_max_retries}次重试后）: {last_error}")

    @staticmethod
    def _ensure_json_hint(system_prompt: str) -> str:
        """确保 system prompt 包含 'json' 关键词，满足 response_format 要求。"""
        if "json" not in system_prompt.lower():
            return system_prompt + "\n请以 JSON 格式返回结果。"
        return system_prompt

    @staticmethod
    def _validate_url(base_url: str) -> None:
        """校验 AI API URL 防止 SSRF（委托给统一安全模块）。"""
        from vocab_qc.core.security import validate_ai_url

        validate_ai_url(base_url)

    @staticmethod
    def _resolve_gateway_provider(model: str) -> str:
        """根据模型名自动推断 Gateway provider，兜底用配置值。"""
        _model_provider_map = {
            "gemini": "VERTEX",
            "gpt": "AZURE",
        }
        model_lower = model.lower().split("|")[0]  # "gpt-5.2|efficiency" → "gpt-5.2"
        for prefix, provider in _model_provider_map.items():
            if model_lower.startswith(prefix):
                return provider
        return settings.ai_gateway_provider  # 兜底

    def _build_request(
        self, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """构造请求参数，委托给模块级公共函数。"""
        return build_ai_request(base_url, api_key, model, system_prompt, user_prompt)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> str:
        """从响应中提取 content，委托给模块级公共函数。"""
        return parse_ai_response(data)

    def _do_request(
        self, base_url: str, api_key: str, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        self._validate_url(base_url)
        url, headers, body = self._build_request(base_url, api_key, model, system_prompt, user_prompt)
        client = _get_http_client()
        t0 = time.monotonic()
        try:
            response = client.post(url, headers=headers, json=body)
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
            logger.info("Gateway async 提交成功 task_no=%s model=%s", task_no, model)
            data = poll_gateway_task_sync(client, base_url, task_no, body)

        content = _strip_markdown_fences(self._parse_response(data))
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise AiRequestError(
                "parse_error", elapsed_ms=elapsed,
                response_body=content[:500], detail=str(e),
            ) from e
