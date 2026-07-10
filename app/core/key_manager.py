"""API Key 管理器 — SQLite 安全存储 + 多供应商管理"""

import json
import sqlite3
import os
from typing import Optional
from dataclasses import dataclass, field

from .crypto import encrypt, decrypt, mask_api_key
from .config import BASE_DIR

DB_PATH = str(BASE_DIR / "api_keys.db")   # 已在 .gitignore 排除


# ---- 供应商元数据 ----
PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "default_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "desc": "综合能力最强，适合复杂质检报告生成",
        "pricing": "输入 $0.15/1M tokens，输出 $0.6/1M tokens",
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_model": "claude-haiku-4-5",
        "default_url": "https://api.anthropic.com/v1",
        "models": ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "desc": "分析推理能力突出，报告结构清晰",
        "pricing": "Haiku $0.80/1M tokens",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "default_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "desc": "国产高性价比，中文质检报告效果好",
        "pricing": "输入 ¥1/1M tokens，输出 ¥2/1M tokens",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "default_model": "qwen-turbo",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen3-235b-a22b"],
        "desc": "阿里云出品，中文质检语义理解出色",
        "pricing": "Turbo 免费额度，Plus ¥0.8/1M tokens",
    },
    "ollama": {
        "name": "Ollama 本地模型",
        "default_model": "qwen3:4b",
        "default_url": "http://localhost:11434/v1",
        "models": ["qwen3:4b", "qwen3:8b", "llama3.2:3b", "gemma3:4b"],
        "desc": "完全免费，离线可用，数据不出本地",
        "pricing": "免费（需本地 GPU/CPU）",
    },
    "zhipu": {
        "name": "智谱 AI (GLM)",
        "default_model": "glm-4-flash",
        "default_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-plus", "glm-4", "glm-4v-plus"],
        "desc": "清华系大模型，GLM-4V 支持多模态图像理解",
        "pricing": "GLM-4-Flash 免费，Plus ¥0.01/1K tokens",
    },
    "baidu": {
        "name": "百度文心 (ERNIE)",
        "default_model": "ernie-speed-128k",
        "default_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-speed-128k", "ernie-4.0-turbo-128k", "ernie-4.5"],
        "desc": "百度千帆平台，ERNIE 4.5 综合能力对标 GPT-4",
        "pricing": "ERNIE-Speed 免费，4.0 ¥0.12/1K tokens",
    },
    "xunfei": {
        "name": "讯飞星火 (Spark)",
        "default_model": "spark-lite",
        "default_url": "https://spark-api-open.xf-yun.com/v1",
        "models": ["spark-lite", "spark-pro", "spark-max", "spark4.0-ultra"],
        "desc": "讯飞出品，语音+文本多模态，中文理解深厚",
        "pricing": "Lite 免费，Pro ¥0.003/1K tokens",
    },
    "hunyuan": {
        "name": "腾讯混元 (Hunyuan)",
        "default_model": "hunyuan-lite",
        "default_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": ["hunyuan-lite", "hunyuan-standard", "hunyuan-pro", "hunyuan-turbo"],
        "desc": "腾讯出品，微信生态集成便利",
        "pricing": "Lite 免费，Standard ¥0.004/1K tokens",
    },
    "moonshot": {
        "name": "月之暗面 (Kimi)",
        "default_model": "moonshot-v1-8k",
        "default_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "desc": "超长上下文 128K，适合批量质检报告生成",
        "pricing": "¥0.012/1K tokens",
    },
    "minimax": {
        "name": "MiniMax (ABAB)",
        "default_model": "abab6.5s-chat",
        "default_url": "https://api.minimax.chat/v1",
        "models": ["abab6.5s-chat", "abab6.5-chat", "abab7-chat"],
        "desc": "海螺AI出品，性价比高，中文优化好",
        "pricing": "abab6.5s ¥0.001/1K tokens",
    },
    "baichuan": {
        "name": "百川智能 (Baichuan)",
        "default_model": "baichuan4",
        "default_url": "https://api.baichuan-ai.com/v1",
        "models": ["baichuan4", "baichuan3-turbo", "baichuan4-air"],
        "desc": "百川大模型，医疗/工业垂类表现突出",
        "pricing": "Baichuan4-Air ¥0.001/1K tokens",
    },
    "lingyi": {
        "name": "零一万物 (Yi)",
        "default_model": "yi-large",
        "default_url": "https://api.lingyiwanwu.com/v1",
        "models": ["yi-large", "yi-medium", "yi-spark", "yi-vision"],
        "desc": "李开复团队，Yi-Vision 多模态理解能力强",
        "pricing": "Yi-Large ¥0.025/1K tokens",
    },
    "doubao": {
        "name": "字节豆包 (Doubao)",
        "default_model": "doubao-lite-128k",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-lite-128k", "doubao-pro-128k", "doubao-pro-32k"],
        "desc": "字节跳动出品，火山引擎部署，128K 超长上下文",
        "pricing": "Lite ¥0.0008/1K tokens（极低）",
    },
}


@dataclass
class ProviderKey:
    provider: str
    api_key_encrypted: str = ""
    model: str = ""
    base_url: str = ""
    is_active: bool = False


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                provider TEXT PRIMARY KEY,
                api_key_encrypted TEXT DEFAULT '',
                model TEXT DEFAULT '',
                base_url TEXT DEFAULT '',
                is_active INTEGER DEFAULT 0
            )
        """)
        # 确保所有供应商都有记录
        for p in PROVIDERS:
            conn.execute(
                "INSERT OR IGNORE INTO api_keys (provider) VALUES (?)", (p,)
            )


def set_key(provider: str, api_key: str, model: str = "", base_url: str = "",
            master_password: str = "vision-inspection-secret") -> bool:
    """保存 API Key（加密存储）"""
    _init_db()
    encrypted = encrypt(api_key, master_password) if api_key else ""
    model = model or PROVIDERS[provider]["default_model"]
    base_url = base_url or PROVIDERS[provider]["default_url"]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (provider, api_key_encrypted, model, base_url, is_active) "
            "VALUES (?, ?, ?, ?, 1)",
            (provider, encrypted, model, base_url),
        )
    return True


def get_key(provider: str, master_password: str = "vision-inspection-secret") -> Optional[ProviderKey]:
    """获取解密后的 Key"""
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT api_key_encrypted, model, base_url, is_active FROM api_keys WHERE provider = ?",
            (provider,),
        ).fetchone()

    if not row:
        return None

    encrypted, model, base_url, is_active = row
    api_key = decrypt(encrypted, master_password) if encrypted else ""
    return ProviderKey(
        provider=provider,
        api_key_encrypted=encrypted,
        model=model or PROVIDERS[provider]["default_model"],
        base_url=base_url or PROVIDERS[provider]["default_url"],
        is_active=bool(is_active) and bool(api_key),
    )


def get_key_masked(provider: str) -> Optional[dict]:
    """获取脱敏后的信息（前端展示用）"""
    pk = get_key(provider)
    if not pk:
        return None

    raw_key = ""
    if pk.api_key_encrypted:
        try:
            raw_key = decrypt(pk.api_key_encrypted, "vision-inspection-secret")
        except Exception:
            raw_key = ""

    return {
        "provider": provider,
        "name": PROVIDERS[provider]["name"],
        "api_key_masked": mask_api_key(raw_key) if raw_key else "",
        "has_key": bool(pk.api_key_encrypted),
        "model": pk.model,
        "base_url": pk.base_url,
        "is_active": pk.is_active and bool(pk.api_key_encrypted),
        "desc": PROVIDERS[provider]["desc"],
        "pricing": PROVIDERS[provider]["pricing"],
        "available_models": PROVIDERS[provider]["models"],
    }


def get_all_providers() -> list[dict]:
    """获取所有供应商状态"""
    _init_db()
    results = []
    with sqlite3.connect(DB_PATH) as conn:
        for provider in PROVIDERS:
            row = conn.execute(
                "SELECT api_key_encrypted, model, base_url, is_active FROM api_keys WHERE provider = ?",
                (provider,),
            ).fetchone()

            has_key = bool(row and row[0])
            results.append({
                "provider": provider,
                "name": PROVIDERS[provider]["name"],
                "has_key": has_key,
                "api_key_masked": mask_api_key(decrypt(row[0], "vision-inspection-secret")) if has_key else "",
                "model": row[1] or PROVIDERS[provider]["default_model"] if row else PROVIDERS[provider]["default_model"],
                "base_url": row[2] or PROVIDERS[provider]["default_url"] if row else PROVIDERS[provider]["default_url"],
                "is_active": bool(row and row[3] and has_key),
                "desc": PROVIDERS[provider]["desc"],
                "pricing": PROVIDERS[provider]["pricing"],
                "available_models": PROVIDERS[provider]["models"],
            })
    return results


def get_active_provider() -> Optional[dict]:
    """获取当前激活的供应商"""
    for p in get_all_providers():
        if p["is_active"]:
            return p
    return None
