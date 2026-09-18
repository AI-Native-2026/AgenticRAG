"""文本切分器（对应学习手册 02 篇）。

切分（Chunking）是整个 RAG 效果的地基：切得太小上下文不足，切得太大检索不精准。
本模块提供两种策略：
1. recursive_splitter ：基于 LlamaIndex SentenceSplitter（按句子边界递归切分，带重叠）
2. heading_splitter   ：基于 Markdown 标题的结构化切分（适合文档/手册类资料，教学对照）

每个 chunk 产出统一结构（与 docstore 字段对齐）：
  {
    "node_id"    : 稳定 id = md5(ref_doc_id + chunk_idx)（幂等，重复跑不会变）
    "ref_doc_id" : 所属文档
    "doc_name"   : 文档名
    "tenant"     : 租户
    "doc_type"   : 文档类型
    "chunk_idx"  : 在文档内的序号
    "text"       : chunk 文本
    "metadata"   : {title, heading, ...} 额外元数据
    "doc_version": 文档版本号
  }
"""

import hashlib
from typing import Dict, List

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


def node_id_of(ref_doc_id: str, chunk_idx: int) -> str:
    """chunk 节点稳定 id。"""
    return "node-" + hashlib.md5(f"{ref_doc_id}:{chunk_idx}".encode("utf-8")).hexdigest()[:16]


class Chunker:
    """将文档列表切成节点列表。"""

    def __init__(self, chunk_size: int | None = None, chunk_overlap: int | None = None):
        env = get_env()
        self.chunk_size = chunk_size or int(env["CHUNK_SIZE"])
        self.chunk_overlap = chunk_overlap or int(env["CHUNK_OVERLAP"])

    def recursive_split(self, doc: Dict[str, str], doc_version: int = 1) -> List[Dict]:
        """LlamaIndex SentenceSplitter：按句子边界递归切分，保持语义完整。"""
        from llama_index.core import Document
        from llama_index.core.node_parser import SentenceSplitter

        splitter = SentenceSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        doc_obj = Document(
            text=doc["text"],
            metadata={"doc_name": doc["doc_name"]},
        )
        nodes = splitter.get_nodes_from_documents([doc_obj])
        return [
            {
                "node_id": node_id_of(doc["ref_doc_id"], i),
                "ref_doc_id": doc["ref_doc_id"],
                "doc_name": doc["doc_name"],
                "tenant": doc["tenant"],
                "doc_type": doc["doc_type"],
                "source_type": doc.get("source_type", "file"),
                "datasource_id": doc.get("datasource_id"),
                "chunk_idx": i,
                "text": node.get_content(),
                "metadata": {"title": node.metadata.get("doc_name", ""), **(doc.get("metadata") or {})},
                "doc_version": doc_version,
            }
            for i, node in enumerate(nodes)
        ]

    def heading_split(self, doc: Dict[str, str], doc_version: int = 1) -> List[Dict]:
        """基于 Markdown 标题的结构化切分（教学对照：结构化资料比纯按字数切更好）。"""
        lines = doc["text"].splitlines()
        chunks: List[Dict] = []
        current_heading = "开头"
        current_lines: List[str] = []
        idx = 0

        for line in lines:
            # 遇到 Markdown 标题（# ~ ####）就收尾上一段、开新段
            stripped = line.strip()
            if stripped.startswith("#") and not stripped.startswith("##"):
                if current_lines:
                    chunks.append(self._make_chunk(doc, idx, current_heading, current_lines, doc_version))
                    idx += 1
                current_heading = stripped.lstrip("#").strip()
                current_lines = []
                continue
            current_lines.append(line)

        if current_lines:
            chunks.append(self._make_chunk(doc, idx, current_heading, current_lines, doc_version))
        return chunks

    def _make_chunk(self, doc, chunk_idx, heading, lines, doc_version) -> Dict:
        text = "\n".join(lines).strip()
        return {
            "node_id": node_id_of(doc["ref_doc_id"], chunk_idx),
            "ref_doc_id": doc["ref_doc_id"],
            "doc_name": doc["doc_name"],
            "tenant": doc["tenant"],
            "doc_type": doc["doc_type"],
            "source_type": doc.get("source_type", "file"),
            "datasource_id": doc.get("datasource_id"),
            "chunk_idx": chunk_idx,
            "text": text,
            "metadata": {"heading": heading, **(doc.get("metadata") or {})},
            "doc_version": doc_version,
        }


if __name__ == "__main__":
    demo_doc = {
        "ref_doc_id": "doc-demo",
        "doc_name": "demo.md",
        "tenant": "tech",
        "doc_type": "md",
        "text": "# 简介\n\n这是一个测试文档。\n\n## 安装方法\n\n第一步安装依赖。\n\n第二步配置环境。\n",
    }
    ch = Chunker()
    print("=== recursive 切分 ===")
    for n in ch.recursive_split(demo_doc):
        print(n["node_id"], "|", n["text"][:30])
    print("=== heading 切分 ===")
    for n in ch.heading_split(demo_doc):
        print(n["metadata"]["heading"], "|", n["text"][:30])
