"""模块6：实时视频流 + WebSocket + MQTT 产线信号"""

import asyncio
import json
import time
import threading
from typing import Optional
import cv2
import numpy as np
from loguru import logger

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

# 最新帧缓存（供 WebSocket 推流）
_latest_frame: Optional[np.ndarray] = None
_frame_lock = threading.Lock()
_streaming = False
_stream_thread: Optional[threading.Thread] = None


def set_frame(frame: np.ndarray):
    global _latest_frame
    with _frame_lock:
        _latest_frame = frame.copy()


def get_frame() -> Optional[np.ndarray]:
    with _frame_lock:
        return _latest_frame.copy() if _latest_frame is not None else None


def encode_jpeg(frame: np.ndarray, quality: int = 75) -> bytes:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def start_rtsp_stream(rtsp_url: str, process_func=None) -> bool:
    """连接 RTSP 工业相机并开始流式检测"""
    global _streaming, _stream_thread

    def _stream_loop():
        global _streaming
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            logger.error(f"无法连接 RTSP 流: {rtsp_url}")
            _streaming = False
            return

        logger.info(f"RTSP 流已连接: {rtsp_url}")
        while _streaming:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue

            if process_func:
                frame = process_func(frame)

            set_frame(frame)
            time.sleep(0.03)

        cap.release()
        logger.info("RTSP 流已断开")

    _streaming = True
    _stream_thread = threading.Thread(target=_stream_loop, daemon=True)
    _stream_thread.start()
    return True


def stop_stream():
    global _streaming
    _streaming = False


def generate_mjpeg():
    """MJPEG 推流生成器（FastAPI StreamingResponse）"""
    while True:
        frame = get_frame()
        if frame is not None:
            jpg = encode_jpeg(frame)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
        time.sleep(0.03)


class MQTTHandler:
    """MQTT 产线信号处理"""

    def __init__(self, broker: str = "localhost", port: int = 1883, topic: str = "defect/alert"):
        self.broker = broker
        self.port = port
        self.topic = topic
        self._client: Optional[mqtt.Client] = None
        self._connected = False

    def connect(self):
        if not HAS_MQTT:
            logger.warning("paho-mqtt 未安装，MQTT 不可用")
            return False

        self._client = mqtt.Client()
        self._client.on_connect = lambda c, u, f, rc: setattr(self, '_connected', True)
        try:
            self._client.connect(self.broker, self.port, 60)
            self._client.loop_start()
            logger.info(f"MQTT 已连接: {self.broker}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"MQTT 连接失败: {e}")
            return False

    def send_defect_alert(self, detection_data: dict, quality_verdict: dict):
        """检测到不合格品 → 发送 MQTT 信号 → PLC 控制分拣"""
        if not self._client:
            return

        payload = json.dumps({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_defects": detection_data.get("total_defects", 0),
            "verdict": quality_verdict.get("verdict", "unknown"),
            "action": "reject" if quality_verdict.get("verdict") == "不合格" else "accept",
        }, ensure_ascii=False)

        self._client.publish(self.topic, payload)
        logger.info(f"MQTT 信号已发送: {self.topic} → {payload[:100]}")

    def continuous_alert(self, detection_data: dict, threshold: int = 3):
        """连续N件不合格 → 触发产线告警"""
        # 维护最近 N 次检测结果
        pass

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()


mqtt_handler = MQTTHandler()
