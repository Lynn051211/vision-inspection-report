"""模块10：数字孪生可视化看板 — 实时指标 + 热力图 + 趋势预警"""

import json
import time
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
from loguru import logger


class InspectionDashboard:
    """产线质检看板 — 实时数据聚合 + 趋势分析"""

    def __init__(self):
        self._history: list[dict] = []       # 检测历史
        self._today_stats = defaultdict(int)  # 今日统计
        self._trend_data: list[dict] = []     # 趋势数据（按小时）
        self._heatmap = defaultdict(int)      # 缺陷热力图数据 ((x_zone, y_zone) → count)
        self._load_history()

    def record(self, detection_data: dict, quality_verdict: dict):
        """记录一次检测结果"""
        record = {
            "time": datetime.now().isoformat(),
            "total_defects": detection_data.get("total_defects", 0),
            "verdict": quality_verdict.get("verdict", "unknown"),
            "inference_ms": detection_data.get("inference_time_ms", 0),
            "classes": detection_data.get("class_summary", {}),
            "defects": detection_data.get("detections", []),
        }

        self._history.append(record)
        self._update_today(record)
        self._update_trend(record)
        self._update_heatmap(record)

        # 定期持久化
        if len(self._history) % 100 == 0:
            self._save_history()

    def _update_today(self, record: dict):
        self._today_stats["total_inspections"] += 1
        if record["verdict"] == "不合格":
            self._today_stats["rejected"] += 1
        elif record["verdict"] == "合格":
            self._today_stats["accepted"] += 1
        self._today_stats["total_defects_found"] += record["total_defects"]

    def _update_trend(self, record: dict):
        """按小时聚合趋势"""
        hour = datetime.now().strftime("%H:00")
        if not self._trend_data or self._trend_data[-1].get("hour") != hour:
            self._trend_data.append({
                "hour": hour, "count": 0, "defects": 0, "rejected": 0,
            })
        self._trend_data[-1]["count"] += 1
        self._trend_data[-1]["defects"] += record["total_defects"]
        if record["verdict"] == "不合格":
            self._trend_data[-1]["rejected"] += 1

    def _update_heatmap(self, record: dict):
        """缺陷位置热力图（将图像划分为 5×5 网格）"""
        for d in record.get("defects", []):
            bbox = d.get("bbox", [0, 0, 0, 0])
            cx = (bbox[0] + bbox[2]) / 2 / 640   # 归一化到 0-1
            cy = (bbox[1] + bbox[3]) / 2 / 640
            zone_x = min(int(cx * 5), 4)
            zone_y = min(int(cy * 5), 4)
            key = f"{zone_x},{zone_y}"
            self._heatmap[key] += 1

    def get_realtime_metrics(self) -> dict:
        """实时指标"""
        return {
            "timestamp": datetime.now().isoformat(),
            "today": dict(self._today_stats),
            "accept_rate": round(
                self._today_stats["accepted"] /
                max(self._today_stats["total_inspections"], 1) * 100, 1
            ),
            "trend": self._trend_data[-24:],  # 最近 24 小时
        }

    def get_heatmap(self) -> dict:
        """缺陷热力图数据"""
        grid = [[0] * 5 for _ in range(5)]
        for key, count in self._heatmap.items():
            x, y = map(int, key.split(","))
            grid[y][x] = count
        return {"grid": grid, "max": max(self._heatmap.values(), default=1)}

    def get_trend_alert(self, increase_threshold: float = 0.2) -> Optional[dict]:
        """趋势预警：缺陷率连续上升 → 预测设备故障"""
        if len(self._trend_data) < 4:
            return None

        recent = self._trend_data[-4:]
        defect_rates = [
            r["rejected"] / max(r["count"], 1) for r in recent
        ]

        # 检查连续上升趋势
        if all(defect_rates[i] <= defect_rates[i + 1] for i in range(len(defect_rates) - 1)):
            increase = defect_rates[-1] - defect_rates[0]
            if increase >= increase_threshold:
                return {
                    "alert": True,
                    "message": f"缺陷率连续上升，从 {defect_rates[0]*100:.1f}% → {defect_rates[-1]*100:.1f}%",
                    "suggestion": "建议检查设备状态或来料质量",
                    "defect_rates": defect_rates,
                }
        return None

    def get_history(self, days: int = 7) -> list[dict]:
        """获取历史记录"""
        cutoff = datetime.now() - timedelta(days=days)
        return [r for r in self._history if datetime.fromisoformat(r["time"]) > cutoff]

    def _save_history(self):
        os.makedirs("data", exist_ok=True)
        with open("data/dashboard_history.json", "w") as f:
            json.dump(self._history[-1000:], f, ensure_ascii=False)

    def _load_history(self):
        path = "data/dashboard_history.json"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self._history = json.load(f)
            except Exception:
                pass


dashboard = InspectionDashboard()
