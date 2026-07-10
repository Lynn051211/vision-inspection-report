"""SSRF 防护 + URL 安全校验"""

import ipaddress
from urllib.parse import urlparse
from html import escape as html_escape


# 内网/回环/保留地址段
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """
    校验 Webhook URL 安全性
    - 仅允许 HTTPS
    - 屏蔽内网/回环/保留地址
    - 返回 (is_safe, reason)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 格式无效"

    if parsed.scheme not in ("https",):
        return False, f"不支持的协议: {parsed.scheme}，仅允许 HTTPS"

    host = parsed.hostname
    if not host:
        return False, "URL 缺少主机名"

    # 校验主机名不是内网地址
    try:
        ip = ipaddress.ip_address(host)
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False, f"禁止访问内网地址: {host}"
    except ValueError:
        pass  # 不是 IP 地址，是域名

    return True, "OK"


def validate_rtsp_url(url: str) -> tuple[bool, str]:
    """
    校验 RTSP URL 安全性
    - 仅允许 rtsp:// 协议
    - 屏蔽内网地址
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 格式无效"

    if parsed.scheme not in ("rtsp", "rtsps"):
        return False, f"不支持的协议: {parsed.scheme}，仅允许 rtsp/rtsps"

    host = parsed.hostname
    if not host:
        return False, "URL 缺少主机名"

    try:
        ip = ipaddress.ip_address(host)
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return False, f"禁止访问内网地址: {host}"
    except ValueError:
        pass

    return True, "OK"


def sanitize_html(text: str) -> str:
    """HTML 转义，防止 XSS"""
    return html_escape(text)
