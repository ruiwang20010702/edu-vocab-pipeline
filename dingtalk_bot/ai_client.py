"""51talk AI Gateway 同步客户端（独立精简版，不依赖主项目）。

复用主项目 core/generators/base.py 的 Gateway 信封格式与响应解析，
但用于交互式问答：同步（async=False）、纯文本（无 response_format）、低温度。
"""

from __future__ import annotations

import uuid

import httpx

# 与主项目 base.py 一致的 model→provider 推断
_MODEL_PROVIDER_MAP = {"gemini": "VERTEX", "gpt": "AZURE"}


class AiError(Exception):
    """AI 调用失败。"""


def resolve_provider(model: str, fallback: str = "") -> str:
    """按模型名推断 Gateway provider，兜底用传入值。"""
    head = model.lower().split("|")[0]
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if head.startswith(prefix):
            return provider
    return fallback


def parse_response(data: dict) -> str:
    """从 Gateway 响应提取文本，兼容 res 包裹格式（同 base.parse_ai_response）。"""
    if "res" in data and "choices" not in data:
        inner = data["res"]
        if inner is None:
            raise AiError(f"Gateway 返回 res=null code={data.get('code')} msg={data.get('message')}")
        data = inner
    choices = data.get("choices")
    if not choices:
        raise AiError(f"响应缺少 choices 字段: {str(data)[:300]}")
    return choices[0]["message"]["content"]


def ask_ai(
    *,
    base_url: str,
    api_key: str,
    model: str,
    biz_type: str,
    system_prompt: str,
    user_prompt: str,
    provider_fallback: str = "VERTEX",
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> str:
    """同步调用 51talk AI Gateway，返回纯文本答案。"""
    body = {
        "model": model,
        "provider": resolve_provider(model, provider_fallback),
        "api_key": api_key,
        "biz_type": biz_type,
        "biz_id": str(uuid.uuid4()),
        "stream": False,
        "async": False,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        "temperature": temperature,
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    try:
        resp = httpx.post(url, headers={"Content-Type": "application/json"}, json=body, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AiError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise AiError(f"请求失败: {exc}") from exc
    return parse_response(resp.json())
