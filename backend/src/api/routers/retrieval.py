"""检索调试路由：返回混合检索与重排得分。"""

import time
from typing import Any, Dict

from fastapi import APIRouter, Request

from src.api.deps import get_bearer
from src.api.schemas import RetrievalRequest

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/search")
def search(request: Request, body: RetrievalRequest):
    user = get_bearer(request)
    svc = request.app.state.svc
    where: Dict[str, Any] = {}
    if user["role"] != "admin":
        where["tenant"] = user["tenant"]
    if body.datasource_id:
        where["datasource_id"] = body.datasource_id
    if body.kb_id:
        kb = svc.kb_store.get(body.kb_id)
        if kb and kb.get("datasource_ids"):
            where["datasource_id"] = {"$in": kb["datasource_ids"]}
    where = where or None

    t0 = time.time()
    candidates = svc.hybrid.retrieve(body.query, final_top_k=body.top_k, where=where)
    recall_ms = round((time.time() - t0) * 1000, 1)
    t0 = time.time()
    ranked = svc.reranker.rerank(body.query, candidates, top_n=body.top_n) if body.rerank else candidates[:body.top_n]
    rerank_ms = round((time.time() - t0) * 1000, 1)

    results = []
    for i, r in enumerate(ranked):
        meta = r.get("metadata", {}) or {}
        results.append({
            "rank": i + 1,
            "node_id": r["node_id"],
            "text": r["text"],
            "doc_name": meta.get("doc_name", ""),
            "source_type": meta.get("source_type", "file"),
            "datasource_id": meta.get("datasource_id", ""),
            "table": meta.get("table"),
            "page": meta.get("page"),
            "vector_score": r.get("vector_score"),
            "bm25_score": r.get("bm25_score"),
            "rrf_score": r.get("rrf_score"),
            "rerank_score": r.get("rerank_score"),
        })
    return {"query": body.query, "candidates": len(candidates), "results": results,
            "recall_ms": recall_ms, "rerank_ms": rerank_ms, "where": where}


@router.get("/stats")
def stats(request: Request):
    get_bearer(request)
    svc = request.app.state.svc
    return svc.stats()
