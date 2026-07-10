"""模块9：数据飞轮 + 主动学习 + 模型增量训练"""

import os
import json
import time
from datetime import datetime
from typing import Optional
from loguru import logger


class DataFlywheel:
    """数据飞轮：收集低置信度样本 → 人工标注 → 增量训练"""

    def __init__(self, storage_dir: str = "data/flywheel"):
        self.storage_dir = storage_dir
        self._uncertain_samples: list[dict] = []
        self._labeled_samples: list[dict] = []
        self._stats = {
            "total_collected": 0,
            "total_labeled": 0,
            "total_trained": 0,
            "last_training": None,
        }
        os.makedirs(storage_dir, exist_ok=True)
        self._load_stats()

    def collect(self, detection_data: dict, uncertainty_threshold: float = 0.6) -> bool:
        """
        收集不确定样本（置信度低于阈值或边界情况）
        返回 True 表示该样本需要人工复核
        """
        dets = detection_data.get("detections", [])
        uncertain = [d for d in dets if d["confidence"] < uncertainty_threshold]

        if not uncertain:
            return False

        sample = {
            "timestamp": datetime.now().isoformat(),
            "image_path": detection_data.get("image_path", ""),
            "uncertain_detections": uncertain,
            "all_detections": dets,
            "status": "pending_review",
        }
        self._uncertain_samples.append(sample)
        self._stats["total_collected"] += 1
        self._save_stats()

        logger.info(f"收集不确定样本: {len(uncertain)}/{len(dets)} 个检测置信度 < {uncertainty_threshold}")
        return True

    def get_review_queue(self) -> list[dict]:
        """获取待人工复核队列"""
        return [s for s in self._uncertain_samples if s["status"] == "pending_review"]

    def submit_review(self, sample_index: int, corrected_labels: list[dict],
                      reviewer: str = "human") -> bool:
        """提交人工标注结果"""
        if sample_index >= len(self._uncertain_samples):
            return False

        sample = self._uncertain_samples[sample_index]
        sample["status"] = "reviewed"
        sample["corrected_labels"] = corrected_labels
        sample["reviewer"] = reviewer
        sample["reviewed_at"] = datetime.now().isoformat()

        self._labeled_samples.append(sample)
        self._stats["total_labeled"] += 1
        self._save_stats()

        # 保存标注结果到 YOLO 格式
        self._save_yolo_annotation(sample)
        return True

    def _save_yolo_annotation(self, sample: dict):
        """将标注结果保存为 YOLO 训练格式"""
        img_path = sample.get("image_path", "")
        if not img_path or not os.path.exists(img_path):
            return

        base = os.path.splitext(os.path.basename(img_path))[0]
        lbl_dir = os.path.join(self.storage_dir, "labels")
        os.makedirs(lbl_dir, exist_ok=True)

        labels = sample.get("corrected_labels", [])
        with open(os.path.join(lbl_dir, f"{base}.txt"), "w") as f:
            for lbl in labels:
                cls_id = lbl.get("class_id", 0)
                xc = lbl.get("x_center", 0.5)
                yc = lbl.get("y_center", 0.5)
                w = lbl.get("width", 0.1)
                h = lbl.get("height", 0.1)
                f.write(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

    def should_retrain(self, min_new_samples: int = 50) -> bool:
        """判断是否需要触发增量训练"""
        return self._stats["total_labeled"] >= min_new_samples

    def trigger_retrain(self) -> dict:
        """触发增量训练（返回训练参数，实际训练由外部调度）"""
        self._stats["total_trained"] += 1
        self._stats["last_training"] = datetime.now().isoformat()
        self._save_stats()

        return {
            "new_samples": self._stats["total_labeled"],
            "labels_dir": os.path.join(self.storage_dir, "labels"),
            "recommended_epochs": min(self._stats["total_labeled"] // 10, 20),
        }

    def ab_test(self, model_a_path: str, model_b_path: str,
                test_images: list[str]) -> dict:
        """A/B 测试：对比两个模型效果"""
        from ultralytics import YOLO
        from app.core.security import validate_model_path

        # 路径安全校验
        for path in [model_a_path, model_b_path]:
            ok, reason = validate_model_path(path)
            if not ok:
                raise ValueError(f"模型路径校验失败 [{path}]: {reason}")

        def _eval(model_path, images):
            model = YOLO(model_path)
            detections = 0
            for img in images:
                results = model(img, verbose=False)
                if results[0].boxes is not None:
                    detections += len(results[0].boxes)
            return detections

        a_count = _eval(model_a_path, test_images)
        b_count = _eval(model_b_path, test_images)

        winner = "A" if a_count > b_count else ("B" if b_count > a_count else "tie")
        return {"model_a_detections": a_count, "model_b_detections": b_count,
                "winner": winner, "auto_switch": winner != "tie"}

    def get_stats(self) -> dict:
        return self._stats

    def _save_stats(self):
        with open(os.path.join(self.storage_dir, "stats.json"), "w") as f:
            json.dump(self._stats, f, indent=2)

    def _load_stats(self):
        path = os.path.join(self.storage_dir, "stats.json")
        if os.path.exists(path):
            with open(path) as f:
                self._stats.update(json.load(f))


flywheel = DataFlywheel()
