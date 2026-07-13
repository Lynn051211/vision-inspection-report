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
        "default_model": "gpt-4.1-mini",
        "default_url": "https://api.openai.com/v1",
        "models": [
            "gpt-5.1", "gpt-5.1-mini", "gpt-5.1-nano",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-4o", "gpt-4o-mini",
            "o5-mini", "o5", "o4-mini", "o3-mini",
        ],
        "desc": "2026 Q3 最新：GPT-5.1 系列旗舰，o5 最强推理模型",
        "pricing": "5.1 $5/$20, 5.1-mini $0.5/$2, o5-mini $2/$8 per 1M",
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_model": "claude-sonnet-4-6",
        "default_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-opus-4-7", "claude-sonnet-4-6",
            "claude-haiku-4-5", "claude-3.5-haiku",
        ],
        "desc": "2026.07：Opus 4.7 编程推理顶级，Sonnet 4.6 性价比之王",
        "pricing": "Opus $15/$75, Sonnet $3/$15, Haiku $0.80/$4 per 1M",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-v4-pro",
        "default_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-v4-pro", "deepseek-v4-flash",
            "deepseek-v3.1", "deepseek-r1-0528",
            "deepseek-v4-turbo",
        ],
        "desc": "2026 Q3：V4 Pro 编程推理顶级，Flash 性价比极高，Turbo 超快",
        "pricing": "V4-Pro ¥2/¥8, V4-Flash ¥0.5/¥2, V4-Turbo ¥0.3/¥1 per 1M",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "default_model": "qwen3-235b-a22b",
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            "qwen3-235b-a22b", "qwen3-max",
            "qwen3-pro", "qwen3-coder-plus",
            "qwen-plus", "qwen-turbo",
            "qwen-vl-max", "qwen3-omni-flash",
        ],
        "desc": "2026 Q3：Qwen3 235B MoE 开源最强，Omni 多模态语音+图像",
        "pricing": "Turbo 免费，Plus ¥0.8, Max ¥2, 235B ¥5/1M",
    },
    "ollama": {
        "name": "Ollama 本地模型",
        "default_model": "qwen3:14b",
        "default_url": "http://localhost:11434/v1",
        "models": [
            "qwen3:14b", "qwen3:8b", "qwen3:4b",
            "deepseek-v4:latest", "deepseek-r1:14b",
            "llama4:latest", "llama4:70b",
            "gemma3:12b", "gemma3:27b",
            "mistral:7b", "phi4:14b",
        ],
        "desc": "2026 Q3：Qwen3/DeepSeek-V4/Llama4/Gemma3/Phi4 全支持",
        "pricing": "完全免费（本地 GPU/CPU）",
    },
    "zhipu": {
        "name": "智谱 AI (GLM)",
        "default_model": "glm-4.5-flash",
        "default_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            "glm-4.5", "glm-4.5-flash",
            "glm-4.5v", "glm-4.5v-flash",
            "glm-z1-air", "glm-z1-airx", "glm-z1-flash",
        ],
        "desc": "2026 Q3：GLM-4.5 系列 + Z1 免费推理，4.5V 多模态视觉",
        "pricing": "Flash 免费，4.5 ¥0.1, 4.5V ¥0.5/1K tokens",
    },
    "baidu": {
        "name": "百度文心 (ERNIE)",
        "default_model": "ernie-4.5-turbo-128k",
        "default_url": "https://qianfan.baidubce.com/v2",
        "models": [
            "ernie-4.5-turbo-128k", "ernie-4.5-8k",
            "ernie-speed-128k", "ernie-speed-8k",
            "ernie-tiny-8k", "ernie-4.5v-8k",
        ],
        "desc": "2026 Q3：ERNIE 4.5 Turbo 128K，中文顶尖，4.5V 多模态",
        "pricing": "Speed/Tiny 免费，4.5 ¥0.12, 4.5V ¥0.8/1K",
    },
    "xunfei": {
        "name": "讯飞星火 (Spark)",
        "default_model": "spark4.0-ultra",
        "default_url": "https://spark-api-open.xf-yun.com/v1",
        "models": [
            "spark4.0-ultra", "spark-max",
            "spark-pro-128k", "spark-lite",
        ],
        "desc": "2026 Q3：Spark4.0 Ultra 深度推理，Pro 128K 长上下文",
        "pricing": "Lite 免费，Pro ¥0.003, Ultra ¥0.03/1K",
    },
    "hunyuan": {
        "name": "腾讯混元 (Hunyuan)",
        "default_model": "hunyuan-turbo-latest",
        "default_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": [
            "hunyuan-turbo-latest", "hunyuan-t1-latest",
            "hunyuan-pro", "hunyuan-lite",
            "hunyuan-vision",
        ],
        "desc": "2026 Q3：Turbo S 极速推理，T1 深度思考，Vision 多模态",
        "pricing": "Lite 免费，Pro ¥0.1, Turbo ¥0.05/1K",
    },
    "moonshot": {
        "name": "月之暗面 (Kimi)",
        "default_model": "kimi-k2-0711-preview",
        "default_url": "https://api.moonshot.cn/v1",
        "models": [
            "kimi-k2-0711-preview", "kimi-k2-thinking",
            "kimi-k2-turbo",
            "moonshot-v1-128k", "moonshot-v1-32k",
        ],
        "desc": "2026 Q3：Kimi K2 旗舰 + Turbo 高速版，Thinking 深度推理",
        "pricing": "K2 ¥0.06, K2-Turbo ¥0.01, V1 ¥0.012/1K",
    },
    "minimax": {
        "name": "MiniMax (ABAB)",
        "default_model": "abab7-chat",
        "default_url": "https://api.minimax.chat/v1",
        "models": [
            "abab7-chat", "abab7-pro",
            "abab6.5s-chat", "abab6.5-chat",
        ],
        "desc": "2026 Q3：ABAB7 最新旗舰 + Pro 增强版，中文流畅自然",
        "pricing": "6.5s ¥0.001, 7 ¥0.01, 7-Pro ¥0.03/1K",
    },
    "baichuan": {
        "name": "百川智能 (Baichuan)",
        "default_model": "baichuan4-turbo",
        "default_url": "https://api.baichuan-ai.com/v1",
        "models": [
            "baichuan4-turbo", "baichuan4",
            "baichuan4-air", "baichuan4-omni",
        ],
        "desc": "2026 Q3：Baichuan4 Turbo 高速，Omni 多模态，医疗优化",
        "pricing": "Air ¥0.001, Turbo ¥0.003, 4 ¥0.01/1K",
    },
    "lingyi": {
        "name": "零一万物 (Yi)",
        "default_model": "yi-turbo",
        "default_url": "https://api.lingyiwanwu.com/v1",
        "models": [
            "yi-turbo", "yi-large",
            "yi-medium", "yi-vision", "yi-lightning",
        ],
        "desc": "2026 Q3：Yi-Vision 多模态，Turbo 高速，Lightning 极速",
        "pricing": "Large ¥0.025, Turbo ¥0.003, Lightning ¥0.001/1K",
    },
    "doubao": {
        "name": "字节豆包 (Doubao)",
        "default_model": "doubao-seed-1.6-flash",
        "default_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": [
            "doubao-seed-1.6", "doubao-seed-1.6-flash",
            "doubao-seed-1.6-lite", "doubao-seed-1.6-pro",
            "doubao-pro-128k",
        ],
        "desc": "2026 Q3：Seed 1.6 Pro 旗舰，Flash 极速 128K，Lite 超低价",
        "pricing": "Lite ¥0.0008, Flash ¥0.004, Pro ¥0.03/1K",
    },
    "xiaomi": {
        "name": "小米 (MiLM)",
        "default_model": "milm-2.5",
        "default_url": "https://api.xiaomimlm.com/v1",
        "models": [
            "milm-2.5", "milm-2.5-turbo", "milm-2.5-mini",
            "milm-2.5-pro",
        ],
        "desc": "2026 Q3：MiLM 2.5 Pro 旗舰，Turbo 高速，端侧部署优化",
        "pricing": "Mini 免费，Turbo ¥0.001, Pro ¥0.008/1K",
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
