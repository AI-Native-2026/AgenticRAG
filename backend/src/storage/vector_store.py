"""ChromaDB VectorStore —— 向量存储 + ANN 检索。

对应概念：学习手册 03 篇。
职责：只保存「向量 + 少量用于过滤的 metadata + 节点原文」，负责高吞吐的 top-k 近似最近邻检索。
- 注意这里再次冗余存了一份 node 文本(chromadb documents 字段)，
  是为了检索时不用回 Mongo 就能返回文本；真相源仍然是 docstore。
- 底层索引：HNSW（内存图索引），距离度量用余弦。

设计细节：
- PersistentClient(path) → 自动持久化到数据盘（SQLite + WAL），详见 03 篇原理讲解
- metadata 里带 node_id / ref_doc_id / tenant / doc_version，支持 where 过滤
- delete_by_ref_doc：用 where={"ref_doc_id": ...} 一次删掉整个文档的向量（增量更新用）
"""

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

import chromadb

from src.config import get_env


class ChromaVectorStore:
    """ChromaDB 向量仓库封装。"""

    def __init__(self, collection_name: str = "agentic_rag_nodes", path: Optional[str] = None):
        env = get_env()
        self.path = path or env["CHROMA_PATH"]
        self.collection_name = collection_name

        self.client = chromadb.PersistentClient(path=self.path)
        # hnsw:space = cosine 让 Chroma 用余弦相似度做检索（与 bge 归一化向量一致）
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------- 写入 ----------

    def add_nodes(
        self,
        nodes: List[Dict[str, Any]],
        embeddings: List[List[float]],
        batch_size: int = 64,
    ) -> None:
        """批量写入节点向量（分批 add，避免一次性超大请求超时）。

        nodes 与 embeddings 必须一一对应，字段需与 docstore 一致。
        """
        for start in range(0, len(nodes), batch_size):
            batch_nodes = nodes[start : start + batch_size]
            batch_emb = embeddings[start : start + batch_size]
            self.collection.add(
                ids=[n["node_id"] for n in batch_nodes],
                embeddings=batch_emb,
                documents=[n["text"] for n in batch_nodes],
                metadatas=[
                    {
                        "ref_doc_id": n["ref_doc_id"],
                        "doc_name": n.get("doc_name", ""),
                        "tenant": n.get("tenant", ""),
                        "doc_type": n.get("doc_type", ""),
                        "source_type": n.get("source_type", "file"),
                        "datasource_id": n.get("datasource_id") or "",
                        "doc_version": n.get("doc_version", 1),
                        "chunk_idx": n.get("chunk_idx", 0),
                    }
                    for n in batch_nodes
                ],
            )

    # ---------- 检索 ----------

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """相似度检索。where 可传 chroma 过滤条件（如 {"tenant": "tech"}）。"""
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.count() or 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: List[Dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for i, node_id in enumerate(ids):
            meta = metas[i] or {}
            # chroma 用 cosine 距离(0~2)，转成相似度(1~-1)便于直观理解
            score = 1.0 - dists[i]
            hits.append({
                "node_id": node_id,
                "text": docs[i],
                "metadata": meta,
                "score": round(score, 4),
            })
        return hits

    # ---------- 维护 ----------

    def delete_by_ref_doc(self, ref_doc_id: str) -> None:
        """按文档删除全部向量（增量更新：文档变更后旧向量要清掉）。"""
        self.collection.delete(where={"ref_doc_id": ref_doc_id})

    def count(self) -> int:
        return self.collection.count()

    def peek(self, limit: int = 3) -> List[Dict[str, Any]]:
        """查看前几条数据，确认写入了什么。"""
        res = self.collection.get(limit=limit, include=["documents", "metadatas"])
        return [
            {"id": i, "doc": d, "meta": m}
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        ]


if __name__ == "__main__":
    vs = ChromaVectorStore()
    print("当前向量数量:", vs.count())
    # 若为空则写入一条演示数据
    if vs.count() == 0:
        vs.add_nodes(
            [
                {
                    "node_id": "demo-vec-1",
                    "ref_doc_id": "demo-doc",
                    "doc_name": "demo.md",
                    "tenant": "demo",
                    "doc_type": "md",
                    "doc_version": 1,
                    "chunk_idx": 0,
                    "text": "ChromaDB 是一个开源向量数据库",
                }
            ],
            embeddings=[[0.1] * 512],
        )
        print("已写入演示向量, count =", vs.count())
        print("peek:", vs.peek(1))
