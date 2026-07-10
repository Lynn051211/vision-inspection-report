"""YOLOv8 目标检测引擎（复用 ultralytics + ONNX）"""

import time
import cv2
import numpy as np
from pathlib import Path
from typing import Optional
from ultralytics import YOLO
from loguru import logger

from app.core.config import settings

# 缺陷类别（可通过配置文件扩展）
DEFECT_CLASSES = [
    "scratch", "crack", "dent", "stain", "burr", "deformation",
]

_model: Optional[YOLO] = None


def init_detector():
    global _model
    model_path = settings.YOLO_MODEL_ABS
    if not Path(model_path).exists():
        logger.warning(f"YOLO 模型不存在: {model_path}，将自动下载 yolov8n.pt")
        model_path = "yolov8n.pt"
    _model = YOLO(str(model_path))
    logger.info(f"YOLO 检测器已加载: {model_path}")


def detect(image: np.ndarray) -> list[dict]:
    """检测图像中的缺陷，返回结构化列表"""
    if _model is None:
        init_detector()

    results = _model(
        image, imgsz=settings.YOLO_IMGSZ, conf=settings.YOLO_CONF, verbose=False,
    )

    detections = []
    h, w = image.shape[:2]
    r = results[0]

    if r.boxes is not None and len(r.boxes) > 0:
        for cls_id, conf, xyxy in zip(
            r.boxes.cls.cpu().numpy().astype(int),
            r.boxes.conf.cpu().numpy(),
            r.boxes.xyxy.cpu().numpy().astype(int),
        ):
            cls_name = DEFECT_CLASSES[cls_id] if cls_id < len(DEFECT_CLASSES) else f"class_{cls_id}"
            b = xyxy.tolist()
            area_pct = round((b[2] - b[0]) * (b[3] - b[1]) / (w * h) * 100, 2)
            detections.append({
                "class": cls_name,
                "confidence": round(float(conf), 4),
                "bbox": [int(b[0]), int(b[1]), int(b[2]), int(b[3])],
                "area_pct": area_pct,
                "center": [int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)],
            })

    # 按置信度降序
    detections.sort(key=lambda x: x["confidence"], reverse=True)
    return detections


def detect_file(image_path: str) -> dict:
    """检测文件路径，返回完整结构化结果"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"无法读取图像: {image_path}")

    t0 = time.perf_counter()
    dets = detect(img)
    elapsed = (time.perf_counter() - t0) * 1000

    # 统计
    class_counts = {}
    for d in dets:
        c = d["class"]
        class_counts[c] = class_counts.get(c, 0) + 1

    return {
        "image_path": image_path,
        "image_size": [img.shape[1], img.shape[0]],
        "inference_time_ms": round(elapsed, 2),
        "total_defects": len(dets),
        "class_summary": class_counts,
        "detections": dets,
    }
