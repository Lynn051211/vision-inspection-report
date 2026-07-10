"""Prompt 模板引擎 — 检测数据 → LLM 可理解的结构化文本"""

# ---- 系统 Prompt ----
SYSTEM_PROMPT = """你是一名资深工业质检专家。你的任务是根据机器视觉检测系统输出的缺陷数据，生成专业、准确、可操作的质检报告。

要求：
1. 使用中文，语言专业但通俗易懂
2. 精确描述每个缺陷的位置和严重程度
3. 给出明确的合格/不合格判定及理由
4. 提供可操作的维修或处理建议
5. 输出 JSON 格式，字段见用户指令"""

# ---- 报告生成 Prompt ----
REPORT_PROMPT = """请根据以下检测数据，生成一份完整的质检报告。

## 检测数据
- 图像尺寸：{image_size}
- 推理耗时：{inference_time_ms}ms
- 缺陷总数：{total_defects} 处
- 缺陷明细：
{detections_text}

## 输出格式（严格 JSON）
```json
{{
  "title": "质检报告标题",
  "summary": "一段话概括整体情况（2-3句）",
  "defects_description": [
    {{
      "index": 1,
      "type": "缺陷类型中文名",
      "location": "精确描述位置（如：右上角、中心偏左）",
      "size": "描述大小（如：约 35×12mm，面积占比 2.3%）",
      "severity": "轻微|中等|严重",
      "suggestion": "处理建议"
    }}
  ],
  "statistics": {{
    "total": {total_defects},
    "by_type": {class_summary_json}
  }},
  "conclusion": {{
    "verdict": "合格|不合格|需复检",
    "reason": "判定理由（2-3句）",
    "action": "建议措施"
  }}
}}
```"""

# ---- 质检判定 Prompt ----
QUALITY_PROMPT = """请根据检测数据和质检标准，判断该产品是否合格。

## 检测数据
{detections_text}

## 质检标准
- 单缺陷面积阈值：{area_threshold}%
- 总缺陷面积阈值：{total_area_threshold}%
- 最大允许缺陷数：{max_defects}

## 输出格式（严格 JSON）
```json
{{
  "verdict": "合格|不合格|需复检",
  "confidence": "高|中|低",
  "reason": "判定理由",
  "risk_level": "低风险|中风险|高风险",
  "actions": ["建议1", "建议2"]
}}
```"""


def build_report_prompt(detection_data: dict) -> tuple[str, str]:
    """构建报告生成 prompt"""
    dets = detection_data.get("detections", [])

    # 缺陷明细文本
    lines = []
    for i, d in enumerate(dets, 1):
        loc = _describe_location(d["bbox"], detection_data.get("image_size", [640, 640]))
        lines.append(
            f"  {i}. {d['class']} | 置信度 {d['confidence']:.2f} | "
            f"位置 {loc} | 面积占比 {d['area_pct']}%"
        )
    detections_text = "\n".join(lines) if lines else "未检测到缺陷"

    # 类别统计 JSON
    class_summary = detection_data.get("class_summary", {})
    class_json = json.dumps(class_summary, ensure_ascii=False)

    user_prompt = REPORT_PROMPT.format(
        image_size=f"{detection_data.get('image_size', [0,0])[0]}x{detection_data.get('image_size', [0,0])[1]}",
        inference_time_ms=detection_data.get("inference_time_ms", 0),
        total_defects=detection_data.get("total_defects", 0),
        detections_text=detections_text,
        class_summary_json=class_json,
    )

    return SYSTEM_PROMPT, user_prompt


def build_quality_prompt(detection_data: dict, area_threshold: float = 3.0,
                         total_area_threshold: float = 5.0, max_defects: int = 5) -> tuple[str, str]:
    """构建质检判定 prompt"""
    dets = detection_data.get("detections", [])

    lines = []
    for d in dets:
        lines.append(f"  - {d['class']}: 面积 {d['area_pct']}%, 置信度 {d['confidence']:.2f}")
    detections_text = "\n".join(lines) if lines else "未检测到缺陷"

    user_prompt = QUALITY_PROMPT.format(
        detections_text=detections_text,
        area_threshold=area_threshold,
        total_area_threshold=total_area_threshold,
        max_defects=max_defects,
    )

    return SYSTEM_PROMPT, user_prompt


def _describe_location(bbox: list, image_size: list) -> str:
    """将 bbox 坐标转为人类可读的位置描述"""
    x1, y1, x2, y2 = bbox
    w, h = image_size
    cx = (x1 + x2) / 2 / w
    cy = (y1 + y2) / 2 / h

    v = "上方" if cy < 0.33 else ("下方" if cy > 0.67 else "中部")
    h_pos = "左侧" if cx < 0.33 else ("右侧" if cx > 0.67 else "中央")
    return f"{v}{h_pos}"


import json
