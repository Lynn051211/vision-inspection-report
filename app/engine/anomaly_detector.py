"""模块7：标准件对比 + 异常检测 + 尺寸测量"""

import cv2
import numpy as np
from typing import Optional, Tuple
from loguru import logger


class StandardComparator:
    """标准件对比检测器"""

    def __init__(self, reference_path: Optional[str] = None):
        self._reference: Optional[np.ndarray] = None
        self._ref_path = reference_path
        if reference_path:
            self.load_reference(reference_path)

    def load_reference(self, path: str):
        """加载标准件（金标准）图像"""
        img = cv2.imread(path)
        if img is None:
            raise ValueError(f"无法加载标准件图像: {path}")
        self._reference = img
        self._ref_path = path
        logger.info(f"标准件已加载: {path} ({img.shape[1]}x{img.shape[0]})")

    def compare(self, test_image: np.ndarray, threshold: int = 30) -> dict:
        """
        待检件 vs 标准件 → 像素级差分 → 异常区域
        返回：差异区域列表、差异面积占比、总体相似度
        """
        if self._reference is None:
            return {"error": "未加载标准件"}

        # 对齐尺寸
        ref = cv2.resize(self._reference, (test_image.shape[1], test_image.shape[0]))

        # 灰度化
        ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        test_gray = cv2.cvtColor(test_image, cv2.COLOR_BGR2GRAY)

        # 差分
        diff = cv2.absdiff(ref_gray, test_gray)
        _, binary = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

        # 形态学处理（去除噪点）
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # 查找异常区域
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        anomalies = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 100:  # 过滤噪声
                x, y, w, h = cv2.boundingRect(cnt)
                anomalies.append({
                    "bbox": [int(x), int(y), int(x + w), int(y + h)],
                    "area_px": int(area),
                    "area_pct": round(area / (test_image.shape[0] * test_image.shape[1]) * 100, 3),
                })

        total_h, total_w = test_image.shape[:2]
        diff_pct = round(np.sum(binary == 255) / (total_h * total_w) * 100, 3)
        similarity = round(100 - diff_pct, 2)

        return {
            "similarity_pct": similarity,
            "diff_area_pct": diff_pct,
            "anomaly_count": len(anomalies),
            "anomalies": sorted(anomalies, key=lambda x: x["area_px"], reverse=True)[:10],
            "verdict": "合格" if diff_pct < 1.0 else ("需复检" if diff_pct < 3.0 else "不合格"),
        }

    def measure(self, image: np.ndarray, bbox: list, reference_mm: float = 50.0,
                reference_px: int = 100) -> dict:
        """
        尺寸测量：已知参照物物理尺寸 → 计算缺陷实际尺寸
        reference_mm: 参照物实际大小（毫米）
        reference_px: 参照物在图中像素数
        """
        scale = reference_mm / reference_px if reference_px > 0 else 1.0
        x1, y1, x2, y2 = bbox
        w_mm = round(abs(x2 - x1) * scale, 2)
        h_mm = round(abs(y2 - y1) * scale, 2)
        area_mm2 = round(w_mm * h_mm, 2)

        return {
            "width_mm": w_mm,
            "height_mm": h_mm,
            "area_mm2": area_mm2,
            "scale_mm_per_px": round(scale, 4),
            "reference_mm": reference_mm,
        }


comparator = StandardComparator()
