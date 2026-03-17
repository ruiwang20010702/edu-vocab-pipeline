"""安全工具函数."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

from vocab_qc.core.config import settings

# XSS 检测正则（re.DOTALL 覆盖换行绕过）
_HTML_TAG_RE = re.compile(r"<\s*/?[a-zA-Z][^>]*?>?", re.DOTALL)
_HTML_ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_DANGEROUS_URI_RE = re.compile(r"(?:javascript|data)\s*:", re.IGNORECASE)


def reject_html_input(text: str | None, field_name: str = "content") -> None:
    """拒绝包含 HTML/XSS 载荷的输入。

    检测：HTML 标签（含不闭合）、事件处理器、HTML 实体、javascript:/data: URI。
    """
    if not text:
        return
    if _HTML_TAG_RE.search(text) or _EVENT_HANDLER_RE.search(text):
        raise HTTPException(status_code=400, detail=f"{field_name} 不允许包含 HTML 标签")
    if _HTML_ENTITY_RE.search(text):
        raise HTTPException(status_code=400, detail=f"{field_name} 不允许包含 HTML 实体编码")
    if _DANGEROUS_URI_RE.search(text):
        raise HTTPException(status_code=400, detail=f"{field_name} 不允许包含危险 URI")


def validate_ai_url(base_url: str) -> None:
    """校验 AI API URL 防止 SSRF。

    解析 DNS 后检查 IP 是否为私有/环回/链路本地地址。
    """
    if getattr(settings, "allow_private_ai_url", False):
        return

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"AI API URL scheme 不合法: {parsed.scheme}")

    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("AI API URL 缺少主机名")

    # Fix 9: 白名单内主机直接放行，跳过 DNS 解析（防 TOCTOU）
    if hostname in settings.allowed_ai_hosts:
        return

    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"禁止使用内网 AI API 地址: {hostname} -> {resolved_ip}")
    except socket.gaierror:
        raise ValueError(f"无法解析 AI API 主机名: {hostname}")
