"""核心业务服务 — 检测 + LLM 分析 + 报告生成"""

from loguru import logger
from app.engine.detector import detect_file
from app.engine.llm_adapter import llm
from app.engine.prompts import build_report_prompt
from app.engine.report_builder import build_structured_report, render_html, render_markdown
from app.engine.quality_checker import dual_check


def run_inspection(image_path: str, generate_report: bool = True,
                   quality_check: bool = True) -> dict:
    """
    完整检测流程：
    1. YOLO 检测
    2. LLM 生成报告（可选）
    3. 质检判定（可选）
    """
    # Step 1: 检测
    logger.info(f"开始检测: {image_path}")
    detection_data = detect_file(image_path)
    logger.info(f"检测完成: {detection_data['total_defects']} 个缺陷, "
                f"{detection_data['inference_time_ms']}ms")

    result = {
        "success": True,
        "detection": detection_data,
    }

    # Step 2: LLM 报告
    if generate_report and detection_data["total_defects"] > 0:
        try:
            sys_prompt, user_prompt = build_report_prompt(detection_data)
            llm_response = llm.chat(sys_prompt, user_prompt, temperature=0.3, max_tokens=2000)
            report = build_structured_report(detection_data, llm_response)
            result["report"] = {
                "json": report,
                "html": render_html(report),
                "markdown": render_markdown(report),
            }
            logger.info("LLM 报告生成完成")
        except Exception as e:
            logger.error(f"LLM 报告生成失败: {e}")
            result["report"] = {"error": str(e)}
    else:
        result["report"] = None

    # Step 3: 质检判定
    if quality_check:
        try:
            verdict = dual_check(detection_data)
            result["quality"] = verdict
            logger.info(f"质检判定: {verdict.get('verdict', '未知')}")
        except Exception as e:
            logger.error(f"质检判定失败: {e}")
            result["quality"] = {"error": str(e)}
    else:
        result["quality"] = None

    return result
