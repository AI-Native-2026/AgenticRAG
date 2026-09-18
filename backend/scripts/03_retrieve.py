"""脚本 03：混合检索 + 重排 演示。

用法：python scripts/03_retrieve.py [--query "你的问题"] [--tenant tech] [--reranker cross_encoder|llm]

教学对照：
  1. 只向量检索 vs 混合检索（看 BM25 对精确词/数字的召回）
  2. cross_encoder 重排 vs llm 重排（看效果与代价）
  3. 租户过滤（多租户数据隔离）
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm.gateway import build_embed_model, setup_settings  # noqa: E402
from src.retrieval.hybrid import HybridRetriever  # noqa: E402
from src.retrieval.rerank import Reranker  # noqa: E402
from src.storage.cache import CacheClient  # noqa: E402
from src.storage.docstore import MongoDocStore  # noqa: E402
from src.storage.vector_store import ChromaVectorStore  # noqa: E402


def build_retriever():
    setup_settings()
    embed = build_embed_model()
    ds = MongoDocStore()
    vs = ChromaVectorStore()
    hybrid = HybridRetriever(embed_model=embed, vector_store=vs)
    hybrid.build_bm25(ds.get_all_nodes())
    return hybrid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="iPhone 17 电池多大")
    parser.add_argument("--tenant", default=None, help="限定租户")
    parser.add_argument("--reranker", default="cross_encoder", choices=["cross_encoder", "llm"])
    parser.add_argument("--no-rerank", action="store_true", help="只看召回不重排")
    args = parser.parse_args()

    hybrid = build_retriever()
    where = {"tenant": args.tenant} if args.tenant else None

    print("=" * 60)
    print(f"查询: {args.query}   租户过滤: {where or '无'}")
    print("=" * 60)

    # 阶段1：混合召回（向量 + BM25 + RRF）
    candidates = hybrid.retrieve(args.query, final_top_k=10, where=where)
    print(f"\n[召回] 共 {len(candidates)} 条候选（RRF 融合）:")
    for c in candidates[:5]:
        print(f"  rrf={c['rrf_score']:.3f} vec={c['vector_score']:.3f} bm25={c['bm25_score']:.1f} | {c['text'][:50]}")

    if args.no_rerank:
        return

    # 阶段2：重排精排
    reranker = Reranker(backend=args.reranker)
    ranked = reranker.rerank(args.query, candidates, top_n=5)
    print(f"\n[重排] backend={args.reranker} 取 top5:")
    for r in ranked:
        doc = r.get("metadata", {}).get("doc_name", "?")
        print(f"  score={r['rerank_score']:.4f} [{doc}] {r['text'][:60]}")


if __name__ == "__main__":
    main()
