"""混合检索：向量 + BM25，RRF 融合（对应学习手册 04 篇）。

流程：
  1. 向量召回 top-k_v（Chroma，语义相似）
  2. 关键词召回 top-k_b（BM25+jieba，精确匹配）
  3. RRF 融合：score(node) = Σ 1/(60 + rank_i) —— 不看各自分数绝对值，
     只看排名，天然避免两种检索的分数不可比问题
  4. 合并去重，返回候选集

RRF（Reciprocal Rank Fusion）为什么好：
  - 两种检索引擎的分数分布完全不同（余弦相似度 vs 词频得分），直接加权没法比
  - RRF 只用排名，鲁棒且无需调权重
"""

import logging
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from llama_index.core.base.embeddings.base import BaseEmbedding

from src.llm.gateway import ModelExecutor
from src.retrieval.bm25 import BM25Retriever
from src.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

RRF_K = 60  # RRF 常数


def _match(meta: Dict[str, Any], where: Dict[str, Any]) -> bool:
    """判断一条命中的 metadata 是否满足过滤条件（支持等值与 $in）。"""
    for k, v in where.items():
        mv = meta.get(k)
        if isinstance(v, dict):
            if "$in" in v and mv not in (v["$in"] or []):
                return False
            if "$ne" in v and mv == v["$ne"]:
                return False
        elif mv != v:
            return False
    return True


class HybridRetriever:
    """向量 + BM25 混合召回器。"""

    def __init__(
        self,
        embed_model: BaseEmbedding,
        vector_store: ChromaVectorStore,
        bm25_retriever: Optional[BM25Retriever] = None,
    ):
        self.embed_model = embed_model
        self.vector_store = vector_store
        self.bm25 = bm25_retriever or BM25Retriever()
        self._dirty = False
        self._node_provider = None

    # ---------- 增量/惰性 BM25 维护 ----------

    def set_node_provider(self, fn) -> None:
        """注入"取全量节点"的回调，用于惰性重建。"""
        self._node_provider = fn

    def mark_dirty(self) -> None:
        """标记索引已过期；下次检索时再重建（避免批量写入时反复重建）。"""
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty and self._node_provider is not None:
            self.build_bm25(self._node_provider())
            self._dirty = False

    def build_bm25(self, nodes: List[Dict]) -> None:
        """用 docstore 全量节点构建 BM25 索引。"""
        self.bm25.build(nodes)
        self._dirty = False
        logger.info("BM25 索引构建完成：%d 节点", len(nodes))

    def retrieve(
        self,
        query: str,
        top_k_v: int = 20,
        top_k_b: int = 20,
        final_top_k: int = 30,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """混合召回，返回 [{node_id, text, metadata, vector_score, bm25_score, rrf_score}]。

        final_top_k 是融合后的候选数，之后交给重排精排。
        """
        self.ensure_fresh()

        # 1) 向量召回 + 2) BM25 召回 并行执行（GPU 与 CPU 互不阻塞）
        from concurrent.futures import ThreadPoolExecutor

        def _vector_recall():
            q_emb = ModelExecutor.embed(self.embed_model, [query])[0]
            return self.vector_store.query(q_emb, top_k=top_k_v, where=where)

        with ThreadPoolExecutor(max_workers=2) as ex:
            f_vec = ex.submit(_vector_recall)
            f_bm = ex.submit(self.bm25.search, query, top_k_b)
            vec_hits = f_vec.result()
            bm_hits = f_bm.result()
        logger.debug("召回：向量 %d / BM25 %d", len(vec_hits), len(bm_hits))

        # 统一按 where 过滤（BM25 是全局索引，必须过滤，否则跨租户泄漏）
        if where:
            vec_hits = [h for h in vec_hits if _match(h.get("metadata") or {}, where)]
            bm_hits = [h for h in bm_hits if _match(h.get("metadata") or {}, where)]

        # 3) RRF 融合
        rrf: Dict[str, Dict] = {}
        for rank, hit in enumerate(vec_hits):
            entry = rrf.setdefault(hit["node_id"], {**hit, "bm25_score": 0.0, "rrf_score": 0.0})
            entry["vector_score"] = hit["score"]
            entry["rrf_score"] += 1.0 / (RRF_K + rank)

        for rank, hit in enumerate(bm_hits):
            if hit["node_id"] not in rrf:
                rrf[hit["node_id"]] = {
                    "node_id": hit["node_id"],
                    "text": hit.get("text", ""),
                    "metadata": hit.get("metadata", {}),
                    "vector_score": 0.0,
                    "bm25_score": hit["score"],
                    "rrf_score": 0.0,
                }
            rrf[hit["node_id"]]["bm25_score"] = hit["score"]
            rrf[hit["node_id"]]["rrf_score"] = rrf[hit["node_id"]].get("rrf_score", 0.0) + 1.0 / (RRF_K + rank)

        results = sorted(rrf.values(), key=lambda x: x["rrf_score"], reverse=True)[:final_top_k]
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.llm.gateway import build_embed_model
    from src.storage.docstore import MongoDocStore
    from src.storage.vector_store import ChromaVectorStore

    embed = build_embed_model()
    vs = ChromaVectorStore()
    ds = MongoDocStore()

    hr = HybridRetriever(embed_model=embed, vector_store=vs)
    hr.build_bm25(ds.get_all_nodes())
    for q in ["苹果发布的新手机", "电动车续航"]:
        hits = hr.retrieve(q, final_top_k=5)
        print(f"\n查询: {q}")
        for h in hits:
            print(f"  rrf={h['rrf_score']:.3f} vec={h['vector_score']} bm25={h['bm25_score']} | {h['text'][:40]}")
