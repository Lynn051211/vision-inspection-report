"""LLM 多供应商适配层 — 统一接口，支持 OpenAI / Claude / DeepSeek / Qwen / Ollama"""

import json
import time
from typing import Optional, Generator
from openai import OpenAI
from loguru import logger

from app.core.key_manager import get_key, PROVIDERS, get_active_provider


class LLMAdapter:
    """多 LLM 统一调用适配器"""

    def __init__(self):
        self._clients = {}
        self._active_provider = None

    def _get_client(self, provider: str) -> Optional[OpenAI]:
        """获取或创建 OpenAI-compatible client"""
        if provider in self._clients:
            return self._clients[provider]

        pk = get_key(provider)
        if not pk or not pk.api_key:
            logger.warning(f"供应商 {provider} 未配置 API Key")
            return None

        base_url = pk.base_url or PROVIDERS[provider]["default_url"]
        client = OpenAI(api_key=pk.api_key, base_url=base_url, timeout=30)
        self._clients[provider] = client
        return client

    def test_connection(self, provider: str) -> dict:
        """测试 LLM 连接是否可用"""
        client = self._get_client(provider)
        if not client:
            return {"ok": False, "error": "未配置 API Key"}

        pk = get_key(provider)
        model = pk.model if pk else PROVIDERS[provider]["default_model"]

        try:
            start = time.time()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "回复 OK"}],
                max_tokens=10,
            )
            elapsed = (time.time() - start) * 1000
            return {
                "ok": True,
                "model": model,
                "provider": PROVIDERS[provider]["name"],
                "latency_ms": round(elapsed, 0),
                "reply": resp.choices[0].message.content.strip(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def chat(self, system_prompt: str, user_prompt: str,
             temperature: float = 0.3, max_tokens: int = 2000,
             stream: bool = False) -> str | Generator:
        """调用当前激活的 LLM 进行对话"""
        provider_info = get_active_provider()
        if not provider_info:
            raise RuntimeError("没有可用的 LLM 供应商，请先配置 API Key")

        provider = provider_info["provider"]
        client = self._get_client(provider)
        if not client:
            raise RuntimeError(f"供应商 {provider} 不可用")

        pk = get_key(provider)
        model = pk.model if pk else PROVIDERS[provider]["default_model"]

        logger.info(f"LLM 调用: provider={provider}, model={model}")

        if stream:
            return client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content


# 全局单例
llm = LLMAdapter()
