"""质检规则引擎 + LLM 双通道判定"""

from loguru import logger
from app.engine.llm_adapter import llm
from app.engine.prompts import build_quality_prompt


def rule_based_check(detection_data: dict, area_threshold: float = 3.0,
                     total_area_threshold: float = 5.0, max_defects: int = 5) -> dict:
    """
    规则引擎快速判定（不调用 LLM）
    """
    dets = detection_data.get("detections", [])
    total_area = sum(d["area_pct"] for d in dets)
    max_single_area = max((d["area_pct"] for d in dets), default=0)

    failures = []
    if max_single_area > area_threshold:
        failures.append(f"单缺陷最大面积 {max_single_area}% > 阈值 {area_threshold}%")
    if total_area > total_area_threshold:
        failures.append(f"总缺陷面积 {total_area:.1f}% > 阈值 {total_area_threshold}%")
    if len(dets) > max_defects:
        failures.append(f"缺陷总数 {len(dets)} > 阈值 {max_defects}")

    return {
        "verdict": "不合格" if failures else "合格",
        "method": "规则引擎",
        "details": {
            "total_area_pct": round(total_area, 2),
            "max_single_area_pct": round(max_single_area, 2),
            "defect_count": len(dets),
        },
        "failures": failures,
    }


def llm_quality_check(detection_data: dict, area_threshold: float = 3.0,
                      total_area_threshold: float = 5.0, max_defects: int = 5) -> dict:
    """
    LLM 智能判定（语义理解 + 解释）
    """
    try:
        sys_prompt, user_prompt = build_quality_prompt(
            detection_data, area_threshold, total_area_threshold, max_defects,
        )
        response = llm.chat(sys_prompt, user_prompt, temperature=0.1, max_tokens=800)

        # 解析 JSON
        import json
        if "```json" in response:
            start = response.index("```json") + 7
            end = response.index("```", start)
            result = json.loads(response[start:end].strip())
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            result = json.loads(response[start:end].strip())
        else:
            result = json.loads(response)

        result["method"] = "LLM 智能判定"
        return result
    except Exception as e:
        logger.error(f"LLM 判定失败: {e}，回退到规则引擎")
        return rule_based_check(detection_data, area_threshold, total_area_threshold, max_defects)


def dual_check(detection_data: dict, area_threshold: float = 3.0,
               total_area_threshold: float = 5.0, max_defects: int = 5) -> dict:
    """
    双通道判定：规则引擎初筛 + LLM 兜底
    - 明显合格/不合格 → 规则引擎快速通过
    - 边界情况 → LLM 做语义判断
    """
    # 先跑规则引擎
    rule_result = rule_based_check(detection_data, area_threshold, total_area_threshold, max_defects)
    dets = detection_data.get("detections", [])

    # 边界情况（缺陷接近阈值）→ 请 LLM
    total_area = sum(d["area_pct"] for d in dets)
    borderline = (
        abs(total_area - total_area_threshold) < 1.0 or
        any(abs(d["area_pct"] - area_threshold) < 0.5 for d in dets)
    )

    if borderline:
        logger.info("边界情况，启用 LLM 深度判定")
        return llm_quality_check(detection_data, area_threshold, total_area_threshold, max_defects)

    return rule_result
