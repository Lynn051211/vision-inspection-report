"""模块5：RAG 缺陷知识库 — 向量检索 + 历史案例匹配 + 维修方案推荐"""

import os
import json
from typing import Optional
from loguru import logger

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


class DefectKnowledgeBase:
    """工业缺陷知识库：检测到缺陷 → 检索历史相似案例 → 推荐维修方案"""

    def __init__(self, persist_dir: str = "data/knowledge_db"):
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None
        if HAS_CHROMA:
            self._init_chroma()

    def _init_chroma(self):
        os.makedirs(self.persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name="defect_cases",
            metadata={"hnsw:space": "cosine"},
        )

    def add_case(self, defect_type: str, description: str, solution: str,
                 severity: str = "中等", image_path: str = "") -> str:
        """添加一条缺陷案例到知识库"""
        if not HAS_CHROMA:
            logger.warning("ChromaDB 未安装，跳过")
            return ""

        doc_id = f"{defect_type}_{len(self._collection.get().get('ids', [])) + 1}"
        metadata = {
            "defect_type": defect_type,
            "severity": severity,
            "solution": solution,
            "image_path": image_path,
        }
        self._collection.add(
            ids=[doc_id],
            documents=[description],
            metadatas=[metadata],
        )
        logger.info(f"知识库已添加: {doc_id}")
        return doc_id

    def search(self, defect_type: str, description: str = "", top_k: int = 5) -> list[dict]:
        """搜索相似缺陷案例"""
        if not HAS_CHROMA or self._collection is None:
            return self._fallback_search(defect_type)

        query = f"{defect_type} {description}".strip()
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        cases = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                dist = results.get("distances", [[0]] * top_k)[0]
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                doc = results["documents"][0][i] if results.get("documents") else ""
                similarity = round(1 - min(dist[i] if isinstance(dist, list) else dist, 1), 2)
                cases.append({
                    "id": doc_id,
                    "defect_type": meta.get("defect_type", ""),
                    "description": doc,
                    "solution": meta.get("solution", ""),
                    "severity": meta.get("severity", ""),
                    "similarity": similarity,
                })
        return cases

    def _fallback_search(self, defect_type: str) -> list[dict]:
        """无 ChromaDB 时的内置知识库兜底"""
        KB = {
            "scratch": {
                "desc": "表面划痕，常见于金属加工和运输过程",
                "solution": "600-800目砂纸打磨 → 清洁 → 重新喷漆/阳极氧化",
                "severity": "轻微-中等",
            },
            "crack": {
                "desc": "材料裂纹，可能导致结构失效",
                "solution": "评估裂纹深度 → <0.5mm打磨修复 → >0.5mm报废或焊接修复",
                "severity": "严重",
            },
            "dent": {
                "desc": "凹坑/凹陷，常见于冲压和装配过程",
                "solution": "热风枪加热 → 专用工具从背面顶出 → 表面平整度检测",
                "severity": "轻微-中等",
            },
            "stain": {
                "desc": "污渍/锈斑，常见于存储和运输",
                "solution": "专用清洁剂擦拭 → 超声波清洗 → 防锈油涂抹",
                "severity": "轻微",
            },
            "burr": {
                "desc": "毛刺，常见于切削和冲压边缘",
                "solution": "去毛刺刀/锉刀手工去除 → 振动研磨 → 边缘倒角",
                "severity": "轻微",
            },
            "deformation": {
                "desc": "变形，常见于受力不均或热处理不当",
                "solution": "评估变形量 → 冷/热矫正 → 重新热处理",
                "severity": "严重",
            },
        }

        info = KB.get(defect_type, {"desc": "未知缺陷", "solution": "需人工评估", "severity": "未知"})
        return [{
            "id": f"builtin_{defect_type}",
            "defect_type": defect_type,
            "description": info["desc"],
            "solution": info["solution"],
            "severity": info["severity"],
            "similarity": 1.0,
            "source": "builtin",
        }]

    def build_prompt_context(self, detections: list[dict]) -> str:
        """为 LLM 构建知识库增强上下文"""
        context_parts = ["## 历史相似案例（知识库检索）\n"]

        for det in detections[:5]:
            cases = self.search(det["class"])
            if cases:
                c = cases[0]
                context_parts.append(
                    f"- **{det['class']}** (置信度 {det['confidence']:.2f}): "
                    f"建议处理方式 — {c['solution']}\n"
                )

        return "\n".join(context_parts)


# 全局单例
kb = DefectKnowledgeBase()
