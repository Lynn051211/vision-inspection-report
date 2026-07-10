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
    html_path = UPLOAD_DIR / f"report_{report_id}.html"
    if not html_path.exists():
        raise HTTPException(404, "报告不存在")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ---- 模块5: RAG 知识库 ----
@router.get("/knowledge/search")
async def search_knowledge(defect_type: str, description: str = "", top_k: int = 5):
    from app.engine.rag_knowledge import kb
    cases = kb.search(defect_type, description, top_k)
    return JSONResponse({"defect_type": defect_type, "cases": cases})


@router.post("/knowledge/add")
async def add_knowledge(defect_type: str, description: str, solution: str, severity: str = "中等"):
    from app.engine.rag_knowledge import kb
    doc_id = kb.add_case(defect_type, description, solution, severity)
    return JSONResponse({"ok": True, "doc_id": doc_id})


# ---- 模块6: 实时视频流 ----
@router.get("/video/stream")
async def video_stream():
    from app.engine.realtime_video import generate_mjpeg
    from fastapi.responses import StreamingResponse
    return StreamingResponse(generate_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/video/rtsp/start")
async def start_rtsp(rtsp_url: str):
    from app.core.security import validate_rtsp_url
    safe, reason = validate_rtsp_url(rtsp_url)
    if not safe:
        raise HTTPException(400, f"RTSP URL 安全校验失败: {reason}")
    from app.engine.realtime_video import start_rtsp_stream
    ok = start_rtsp_stream(rtsp_url)
    return JSONResponse({"ok": ok})


@router.post("/video/rtsp/stop")
async def stop_rtsp():
    from app.engine.realtime_video import stop_stream
    stop_stream()
    return JSONResponse({"ok": True})


# ---- 模块7: 标准件对比 ----
@router.post("/compare")
async def compare_with_standard(file: UploadFile = File(...), threshold: int = 30):
    from app.engine.anomaly_detector import comparator
    ext = os.path.splitext(file.filename or "image.jpg")[1]
    save_path = UPLOAD_DIR / f"compare_{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(await file.read())
    img = cv2.imread(str(save_path))
    result = comparator.compare(img, threshold)
    return JSONResponse({"success": True, **result})


@router.post("/compare/reference")
async def load_reference(file: UploadFile = File(...)):
    from app.engine.anomaly_detector import comparator
    save_path = UPLOAD_DIR / "reference_standard.jpg"
    save_path.write_bytes(await file.read())
    comparator.load_reference(str(save_path))
    return JSONResponse({"ok": True, "path": str(save_path)})


@router.post("/measure")
async def measure_defect(bbox: str, reference_mm: float = 50.0, reference_px: int = 100,
                         file: UploadFile = File(...)):
    from app.engine.anomaly_detector import comparator
    save_path = UPLOAD_DIR / f"measure_{uuid.uuid4().hex}.jpg"
    save_path.write_bytes(await file.read())
    img = cv2.imread(str(save_path))
    bbox_list = [int(x) for x in bbox.split(",")]
    result = comparator.measure(img, bbox_list, reference_mm, reference_px)
    return JSONResponse({"success": True, **result})


# ---- 模块8: 消息推送 ----
@router.post("/notify/configure")
async def configure_notification(channel: str, webhook_url: str, **kwargs):
    from app.core.security import validate_webhook_url
    safe, reason = validate_webhook_url(webhook_url)
    if not safe:
        raise HTTPException(400, f"URL 安全校验失败: {reason}")
    from app.engine.notifier import notifier
    notifier.configure(channel, webhook_url, **kwargs)
    return JSONResponse({"ok": True, "channel": channel})


@router.post("/notify/send")
async def send_notification(channel: str, title: str, content: str, image_url: str = ""):
    from app.engine.notifier import notifier
    ok = notifier.send(channel, title, content, image_url)
    return JSONResponse({"ok": ok})


# ---- 模块9: 数据飞轮 ----
@router.get("/flywheel/stats")
async def flywheel_stats():
    from app.engine.data_flywheel import flywheel
    return JSONResponse(flywheel.get_stats())


@router.get("/flywheel/review-queue")
async def flywheel_review_queue():
    from app.engine.data_flywheel import flywheel
    return JSONResponse(flywheel.get_review_queue())


@router.post("/flywheel/submit-review")
async def flywheel_submit_review(sample_index: int, corrected_labels: list[dict]):
    from app.engine.data_flywheel import flywheel
    ok = flywheel.submit_review(sample_index, corrected_labels)
    return JSONResponse({"ok": ok})


@router.post("/flywheel/ab-test")
async def flywheel_ab_test(model_a: str, model_b: str, test_images: list[str]):
    from app.engine.data_flywheel import flywheel
    result = flywheel.ab_test(model_a, model_b, test_images)
    return JSONResponse(result)


# ---- 模块10: 数字孪生看板 ----
@router.get("/dashboard/realtime")
async def dashboard_realtime():
    from app.engine.dashboard import dashboard
    return JSONResponse(dashboard.get_realtime_metrics())


@router.get("/dashboard/heatmap")
async def dashboard_heatmap():
    from app.engine.dashboard import dashboard
    return JSONResponse(dashboard.get_heatmap())


@router.get("/dashboard/trend-alert")
async def dashboard_trend_alert():
    from app.engine.dashboard import dashboard
    alert = dashboard.get_trend_alert()
    return JSONResponse(alert or {"alert": False})
