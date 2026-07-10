"""Pydantic Settings 全局配置"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False,
    )

    APP_NAME: str = "智能视觉报告生成与多模态质检系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ---- 模型 ----
    YOLO_MODEL_PATH: str = "models/yolov8n.pt"
    YOLO_CONF: float = 0.35
    YOLO_IMGSZ: int = 640

    # ---- LLM 默认配置 ----
    LLM_PROVIDER: str = "openai"    # openai | claude | ollama | deepseek | qwen
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = ""
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2000

    # ---- 服务 ----
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ---- 加密 ----
    ENCRYPTION_KEY: str = ""        # AES-256 密钥（首次启动自动生成）

    # ---- 数据库 ----
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/vision_inspection.db"

    @property
    def YOLO_MODEL_ABS(self) -> Path:
        p = Path(self.YOLO_MODEL_PATH)
        return p if p.is_absolute() else BASE_DIR / p


settings = Settings()
