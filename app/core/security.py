"""SSRF 防护 + URL 安全校验 + 邮件头注入防护"""

import ipaddress
import socket
from urllib.parse import urlparse
from html import escape as html_escape
from pathlib import Path


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
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("198.18.0.0/15"),   # benchmark
]


def _is_blocked_ip(host: str) -> tuple[bool, str]:
    """检查 IP/域名是否指向内网地址（含 DNS 重绑定防护）"""
    # 先检查是否是 IP 字面量
    try:
        ip = ipaddress.ip_address(host)
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return True, f"禁止访问内网地址: {host}"
        return False, ""
    except ValueError:
        pass  # 不是 IP，需要 DNS 解析

    # DNS 重绑定防护：解析域名并检查结果
    try:
        resolved = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in resolved:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for net in _BLOCKED_NETWORKS:
                if ip in net:
                    return True, f"域名 {host} 解析到内网地址 {ip_str}，已拦截（DNS 重绑定防护）"
    except socket.gaierror:
        return True, f"无法解析域名: {host}"
    except Exception:
        return True, f"DNS 解析异常: {host}"

    return False, ""


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """
    校验 Webhook URL 安全性
    - 仅允许 HTTPS
    - 屏蔽内网/回环/保留地址
    - DNS 重绑定防护
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

    blocked, reason = _is_blocked_ip(host)
    if blocked:
        return False, reason

    return True, "OK"


def validate_rtsp_url(url: str) -> tuple[bool, str]:
    """校验 RTSP URL（仅允许 rtsp/rtsps，屏蔽内网）"""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "URL 格式无效"

    if parsed.scheme not in ("rtsp", "rtsps"):
        return False, f"不支持的协议: {parsed.scheme}，仅允许 rtsp/rtsps"

    host = parsed.hostname
    if not host:
        return False, "URL 缺少主机名"

    blocked, reason = _is_blocked_ip(host)
    if blocked:
        return False, reason

    return True, "OK"


def sanitize_html(text: str) -> str:
    """HTML 转义，防止 XSS"""
    return html_escape(text)


def sanitize_email_header(text: str) -> str:
    """防止邮件头注入：移除 CRLF，截断过长文本"""
    # CRLF 注入防护
    text = text.replace("\r", "").replace("\n", " ")
    # 限制长度
    return text[:200]


def validate_model_path(path: str, base_dir: str = "models") -> tuple[bool, str]:
    """校验模型路径，防止路径遍历攻击"""
    p = Path(path).resolve()
    base = Path(base_dir).resolve()

    # 允许当前目录下的相对路径
    if not p.exists():
        # 路径不存在时，检查是否在 base_dir 内
        try:
            p.resolve().relative_to(base)
        except ValueError:
            return False, f"模型路径必须在 {base_dir}/ 目录下"
        return True, "OK"

    # 存在则直接校验
    try:
        p.relative_to(base)
    except ValueError:
        return False, f"模型路径必须在 {base_dir}/ 目录下"

    return True, "OK"
