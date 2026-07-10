"""模块8：移动端 + 消息推送（钉钉/企业微信/邮件/Webhook）"""

import json
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from loguru import logger

import requests


class NotificationService:
    """多渠道消息推送服务"""

    def __init__(self):
        self._configs = {}

    def configure(self, channel: str, webhook_url: str = "", **kwargs):
        """配置推送渠道"""
        self._configs[channel] = {"webhook_url": webhook_url, **kwargs}
        logger.info(f"推送渠道已配置: {channel}")

    def send(self, channel: str, title: str, content: str, image_url: str = ""):
        """发送通知到指定渠道"""
        if channel not in self._configs:
            logger.warning(f"渠道未配置: {channel}")
            return False

        threading.Thread(
            target=self._send_async, args=(channel, title, content, image_url),
            daemon=True,
        ).start()
        return True

    def _send_async(self, channel: str, title: str, content: str, image_url: str):
        config = self._configs[channel]
        webhook = config.get("webhook_url", "")

        try:
            if channel == "dingtalk":
                self._send_dingtalk(webhook, title, content)
            elif channel == "wecom":
                self._send_wecom(webhook, title, content, image_url)
            elif channel == "email":
                self._send_email(config, title, content)
            elif channel == "webhook":
                self._send_webhook(webhook, title, content, image_url)
            logger.info(f"通知已发送: {channel}")
        except Exception as e:
            logger.error(f"通知发送失败 [{channel}]: {e}")

    def _send_dingtalk(self, webhook: str, title: str, content: str):
        """钉钉机器人 Markdown 消息"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"## {title}\n\n{content}\n\n> 智能视觉质检系统",
            },
        }
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"钉钉返回 {resp.status_code}: {resp.text}")

    def _send_wecom(self, webhook: str, title: str, content: str, image_url: str):
        """企业微信机器人消息"""
        articles = [{
            "title": title,
            "description": content[:500],
            "url": image_url or "about:blank",
            "picurl": image_url or "",
        }]
        payload = {"msgtype": "news", "news": {"articles": articles}}
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"企微返回 {resp.status_code}")

    def _send_email(self, config: dict, title: str, content: str):
        """SMTP 邮件通知"""
        from app.core.security import sanitize_email_header
        msg = MIMEMultipart("alternative")
        msg["Subject"] = sanitize_email_header(title)
        msg["From"] = config.get("smtp_user", "")
        msg["To"] = config.get("to_email", "")

        from app.core.security import sanitize_html
        html = f"<h2>{sanitize_html(title)}</h2><pre style='font-size:14px'>{sanitize_html(content)}</pre>"
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL(config.get("smtp_host", "smtp.qq.com"),
                               config.get("smtp_port", 465)) as server:
            server.login(config.get("smtp_user", ""), config.get("smtp_pass", ""))
            server.sendmail(msg["From"], [msg["To"]], msg.as_string())

    def _send_webhook(self, webhook: str, title: str, content: str, image_url: str):
        """通用 Webhook POST"""
        payload = {"title": title, "content": content, "image_url": image_url,
                   "timestamp": __import__("datetime").datetime.now().isoformat()}
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code >= 400:
            raise Exception(f"Webhook 返回 {resp.status_code}")

    def alert_on_defect(self, detection_data: dict, quality_verdict: dict):
        """缺陷告警：根据判定结果自动推送"""
        verdict = quality_verdict.get("verdict", "")
        total = detection_data.get("total_defects", 0)

        if verdict == "不合格":
            title = f"[质检告警] 产品不合格 — {total}处缺陷"
        elif total > 0:
            title = f"[质检提示] 检测到 {total} 处缺陷"
        else:
            return  # 无缺陷不发通知

        defects_text = "\n".join(
            f"- {d['class']}: 面积{d['area_pct']}%, 置信度{d['confidence']:.2f}"
            for d in detection_data.get("detections", [])[:5]
        )
        content = f"{verdict} | {total}处缺陷\n\n{defects_text}"

        for channel in self._configs:
            self.send(channel, title, content)


notifier = NotificationService()
