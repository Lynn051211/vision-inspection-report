"""报告结构化构建 + 渲染引擎"""

import json
from typing import Optional


def build_structured_report(detection_data: dict, llm_response: str) -> dict:
    """
    将 LLM 返回的 JSON 和检测数据合并为完整报告结构
    """
    # 尝试解析 LLM JSON
    try:
        # 提取 JSON 块
        if "```json" in llm_response:
            start = llm_response.index("```json") + 7
            end = llm_response.index("```", start)
            llm_json = json.loads(llm_response[start:end].strip())
        elif "```" in llm_response:
            start = llm_response.index("```") + 3
            end = llm_response.index("```", start)
            llm_json = json.loads(llm_response[start:end].strip())
        else:
            llm_json = json.loads(llm_response)
    except (json.JSONDecodeError, ValueError):
        # LLM 返回格式错误，使用原始文本
        llm_json = {"raw_response": llm_response}

    # 组装完整报告
    report = {
        "meta": {
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "image_path": detection_data.get("image_path", ""),
            "inference_time_ms": detection_data.get("inference_time_ms", 0),
        },
        "detection": {
            "total_defects": detection_data.get("total_defects", 0),
            "class_summary": detection_data.get("class_summary", {}),
            "detections": detection_data.get("detections", []),
        },
        "analysis": llm_json,
    }
    return report


def render_html(report: dict) -> str:
    """将报告渲染为 HTML"""
    det = report.get("detection", {})
    analysis = report.get("analysis", {})
    meta = report.get("meta", {})
    conclusion = analysis.get("conclusion", {})
    verdict = conclusion.get("verdict", "未知")
    verdict_color = {
        "合格": "#10b981", "不合格": "#ef4444", "需复检": "#f59e0b"
    }.get(verdict, "#666")

    defects_html = ""
    for d in det.get("detections", []):
        defects_html += f"""
        <tr>
          <td>{d['class']}</td>
          <td>{d['confidence']:.2f}</td>
          <td>({d['bbox'][0]},{d['bbox'][1]})-({d['bbox'][2]},{d['bbox'][3]})</td>
          <td>{d['area_pct']}%</td>
        </tr>"""

    descriptions_html = ""
    for item in analysis.get("defects_description", []):
        sev_color = {"轻微": "#fbbf24", "中等": "#f59e0b", "严重": "#ef4444"}.get(
            item.get("severity", ""), "#666")
        descriptions_html += f"""
        <div style="border-left:3px solid {sev_color};padding:8px 12px;margin:8px 0;background:rgba(255,255,255,.03)">
          <strong>#{item.get('index','?')} {item.get('type','')}</strong>
          <span style="color:{sev_color};float:right">{item.get('severity','')}</span>
          <p style="color:#999;margin:4px 0">{item.get('location','')} | {item.get('size','')}</p>
          <p style="margin:4px 0">{item.get('suggestion','')}</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><title>{analysis.get('title', '质检报告')}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1923;color:#e0e0e0;padding:40px}}
.header{{text-align:center;margin-bottom:30px}}
h1{{color:#4ade80;font-size:24px}}
.verdict{{display:inline-block;padding:8px 24px;border-radius:20px;font-size:20px;font-weight:700;margin:16px 0;
  background:{verdict_color};color:#000}}
.meta{{color:#666;font-size:13px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}}
.card{{background:#1a2a3a;border-radius:12px;padding:20px}}
.card h3{{color:#4ade80;margin-bottom:12px;font-size:16px}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:8px;color:#4ade80;font-size:13px;border-bottom:2px solid #2a3a4a}}
td{{padding:8px;font-size:13px;border-bottom:1px solid #2a3a4a}}
.summary{{background:#1a2a3a;border-radius:12px;padding:20px;margin:20px 0;line-height:1.8}}
.conclusion{{background:#1a2a3a;border-radius:12px;padding:20px;margin:20px 0}}
.conclusion h3{{color:{verdict_color}}}
.footer{{text-align:center;color:#444;margin-top:40px;font-size:12px}}
</style></head><body>
<div class="header">
  <h1>{analysis.get('title', '质检报告')}</h1>
  <div class="verdict">{verdict}</div>
  <p class="meta">推理耗时: {meta.get('inference_time_ms', 'N/A')}ms | 生成时间: {meta.get('generated_at', '')}</p>
</div>
<div class="summary"><p>{analysis.get('summary', '')}</p></div>
<div class="grid">
  <div class="card">
    <h3>缺陷检测明细</h3>
    <table><tr><th>类型</th><th>置信度</th><th>位置 (bbox)</th><th>面积</th></tr>
    {defects_html}</table>
    <p style="margin-top:8px;color:#999;font-size:13px">共 {det.get('total_defects', 0)} 处缺陷</p>
  </div>
  <div class="card">
    <h3>缺陷描述</h3>
    {descriptions_html}
  </div>
</div>
<div class="conclusion">
  <h3>结论: {verdict}</h3>
  <p style="margin:8px 0">{conclusion.get('reason', '')}</p>
  <p style="color:#4ade80">{conclusion.get('action', '')}</p>
</div>
<div class="footer">智能视觉报告生成与多模态质检系统 v1.0.0 | AI 生成，仅供参考</div>
</body></html>"""


def render_markdown(report: dict) -> str:
    """将报告渲染为 Markdown"""
    analysis = report.get("analysis", {})
    det = report.get("detection", {})
    conclusion = analysis.get("conclusion", {})

    md = f"# {analysis.get('title', '质检报告')}\n\n"
    md += f"**判定**: {conclusion.get('verdict', '未知')}\n\n"
    md += f"{analysis.get('summary', '')}\n\n"
    md += "## 缺陷明细\n\n"
    md += "| # | 类型 | 置信度 | 位置 | 面积 |\n"
    md += "|---|------|--------|------|------|\n"
    for d in det.get("detections", []):
        md += f"| | {d['class']} | {d['confidence']:.2f} | {d['bbox']} | {d['area_pct']}% |\n"
    md += f"\n共 {det.get('total_defects', 0)} 处缺陷\n\n"
    md += "## 结论\n\n"
    md += f"**{conclusion.get('verdict', '')}**: {conclusion.get('reason', '')}\n\n"
    md += f"建议措施: {conclusion.get('action', '')}\n"

    return md
