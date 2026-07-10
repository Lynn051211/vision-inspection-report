"""FastAPI 路由 — 检测 + 报告 + 质检 + 供应商管理"""

import os
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from loguru import logger

from app.engine.detector import detect_file, detect
from app.engine.report_builder import render_html
from app.engine.quality_checker import dual_check, rule_based_check
from app.engine.llm_adapter import llm
from app.core.key_manager import (
    get_all_providers, get_key_masked, set_key, PROVIDERS,
)

router = APIRouter(prefix="/api/v1", tags=["inspection"])

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "vision-inspection-report"}


# ---- 检测 ----
@router.post("/detect")
async def detect_image(file: UploadFile = File(...)):
    """上传图像，返回 YOLO 检测结果"""
    if file.content_type not in ("image/jpeg", "image/png", "image/bmp"):
        raise HTTPException(400, "仅支持 jpg/png/bmp")

    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(await file.read())

    try:
        result = detect_file(str(save_path))
        return JSONResponse({"success": True, **result})
    except Exception as e:
        raise HTTPException(500, f"检测失败: {e}")


# ---- 报告生成 ----
@router.post("/generate-report")
async def generate_report(file: UploadFile = File(...)):
    """上传图像 → 检测 → LLM 报告生成"""
    from app.services.inspection_service import run_inspection

    if file.content_type not in ("image/jpeg", "image/png", "image/bmp"):
        raise HTTPException(400, "仅支持 jpg/png/bmp")

    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(await file.read())

    try:
        result = run_inspection(str(save_path), generate_report=True, quality_check=True)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(500, f"报告生成失败: {e}")


# ---- 质检判定 ----
@router.post("/quality-check")
async def quality_check(
    file: UploadFile = File(...),
    area_threshold: float = 3.0,
    total_area_threshold: float = 5.0,
    max_defects: int = 5,
):
    """上传图像 → 检测 → 合格判定"""
    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(await file.read())

    detection_data = detect_file(str(save_path))
    verdict = dual_check(detection_data, area_threshold, total_area_threshold, max_defects)

    return JSONResponse({
        "success": True,
        "detection": detection_data,
        "quality": verdict,
    })


# ---- 供应商管理 ----
@router.get("/providers")
async def list_providers():
    """获取所有 LLM 供应商信息"""
    return JSONResponse(get_all_providers())


@router.get("/providers/{provider}")
async def get_provider(provider: str):
    """获取单个供应商详情"""
    info = get_key_masked(provider)
    if not info:
        raise HTTPException(404, f"供应商不存在: {provider}")
    return JSONResponse(info)


@router.post("/providers/{provider}")
async def save_provider(provider: str, data: dict):
    """保存 API Key"""
    if provider not in PROVIDERS:
        raise HTTPException(400, f"不支持的供应商: {provider}")

    api_key = data.get("api_key", "")
    model = data.get("model", "")
    base_url = data.get("base_url", "")

    set_key(provider, api_key, model, base_url)
    logger.info(f"供应商 {provider} 配置已保存")

    return JSONResponse({"ok": True, "provider": provider})


@router.post("/providers/{provider}/test")
async def test_provider(provider: str):
    """测试 LLM 连接"""
    result = llm.test_connection(provider)
    return JSONResponse(result)


# ---- 报告渲染 ----
@router.get("/report/{report_id}")
async def view_report(report_id: str):
    """查看 HTML 报告"""
    html_path = UPLOAD_DIR / f"report_{report_id}.html"
    if not html_path.exists():
        raise HTTPException(404, "报告不存在")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
