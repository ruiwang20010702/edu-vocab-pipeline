"""安全工具函数."""

import ipaddress
import socket
from urllib.parse import urlparse

from vocab_qc.core.config import settings


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

    try:
        resolved_ip = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"禁止使用内网 AI API 地址: {hostname} -> {resolved_ip}")
    except socket.gaierror:
        raise ValueError(f"无法解析 AI API 主机名: {hostname}")
