"""检索调试路由：混合检索、以图搜图、媒体文件访问。"""

import os
import tempfile
import time
from typing import Any, Dict

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse

from src.api.deps import AppError, get_bearer
from src.api.schemas import RetrievalRequest

router = APIRouter(prefix="/v1", tags=["retrieval"])


def _where_for(svc, user: Dict[str, Any], kb_id=None, datasource_id=None) -> Dict[str, Any]:
    where: Dict[str, Any] = {}
    if user["role"] != "admin":
        where["tenant"] = user["tenant"]
    if datasource_id:
        where["datasource_id"] = datasource_id
    if kb_id:
        kb = svc.kb_store.get(kb_id)
        if kb and kb.get("datasource_ids"):
            where["datasource_id"] = {"$in": kb["datasource_ids"]}
    return where or None


def _serialize(results) -> list:
    out = []
    for i, r in enumerate(results):
        meta = r.get("metadata", {}) or {}
        out.append({
            "rank": i + 1,
            "node_id": r["node_id"],
            "text": r["text"],
            "doc_name": meta.get("doc_name", ""),
            "source_type": meta.get("source_type", "file"),
            "datasource_id": meta.get("datasource_id", ""),
            "modality": meta.get("modality", "text"),
            "media_path": meta.get("media_path", ""),
            "table": meta.get("table"),
            "page": meta.get("page"),
            "vector_score": r.get("vector_score"),
            "bm25_score": r.get("bm25_score"),
            "rrf_score": r.get("rrf_score"),
            "rerank_score": r.get("rerank_score"),
        })
    return out


@router.post("/retrieval/search")
def search(request: Request, body: RetrievalRequest):
    user = get_bearer(request)
    svc = request.app.state.svc
    where = _where_for(svc, user, body.kb_id, body.datasource_id)

    t0 = time.time()
    candidates = svc.hybrid.retrieve(body.query, final_top_k=body.top_k, where=where)
    recall_ms = round((time.time() - t0) * 1000, 1)
    t0 = time.time()
    ranked = svc.reranker.rerank(body.query, candidates, top_n=body.top_n) if body.rerank else candidates[:body.top_n]
    rerank_ms = round((time.time() - t0) * 1000, 1)

    return {"query": body.query, "candidates": len(candidates), "results": _serialize(ranked),
            "recall_ms": recall_ms, "rerank_ms": rerank_ms, "where": where}


@router.post("/retrieval/search-by-image")
async def search_by_image(request: Request, file: UploadFile = File(...), top_n: int = 5,
                          modality: str = ""):
    """以图搜图 / 以图搜内容。

    - modality=image：只返回图片（视觉相似图片）
    - modality 为空：返回所有类型（图片 / 文本 / 表格）中与图片语义相似的内容
    """
    user = get_bearer(request)
    svc = request.app.state.svc
    embedder = svc.embedder
    if not getattr(embedder, "supports_image", False):
        raise AppError(400, "NOT_SUPPORTED",
                       "当前未启用多模态 Embedding（设置 EMBED_BACKEND=vl 后可用）")

    suffix = os.path.splitext(file.filename or "query.png")[1] or ".png"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(await file.read())
        q_emb = embedder.embed_items([{"modality": "image", "media_path": tmp}])[0]
        where = _where_for(svc, user)
        # 需要按类型过滤时多召回一些，过滤后再截断
        k = top_n if not modality else max(top_n * 5, 20)
        hits = svc.vector_store.query(q_emb, top_k=k, where=where)
        if modality:
            hits = [h for h in hits if (h.get("metadata") or {}).get("modality") == modality]
        hits = hits[:top_n]
        results = [{
            "rank": i + 1, "node_id": h["node_id"], "text": h["text"],
            "doc_name": (h.get("metadata") or {}).get("doc_name", ""),
            "source_type": (h.get("metadata") or {}).get("source_type", ""),
            "datasource_id": (h.get("metadata") or {}).get("datasource_id", ""),
            "modality": (h.get("metadata") or {}).get("modality", "text"),
            "media_path": (h.get("metadata") or {}).get("media_path", ""),
            "vector_score": h.get("score"),
        } for i, h in enumerate(hits)]
        return {"query_image": file.filename, "modality": modality or "all", "results": results}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


@router.get("/media/{node_id}")
def media(node_id: str, request: Request):
    """按 node_id 返回原始媒体文件（校验租户归属）。"""
    user = get_bearer(request)
    svc = request.app.state.svc
    node = svc.docstore.get_node(node_id)
    if not node:
        raise AppError(404, "NOT_FOUND", "节点不存在")
    if user["role"] != "admin" and node.get("tenant") != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权访问")
    path = (node.get("metadata") or {}).get("media_path")
    if not path or not os.path.exists(path):
        raise AppError(404, "NOT_FOUND", "媒体文件不存在")
    return FileResponse(path)


@router.get("/retrieval/stats")
def stats(request: Request):
    get_bearer(request)
    svc = request.app.state.svc
    s = svc.stats()
    s["embed_backend"] = svc.embedder.name
    s["embed_dim"] = svc.embedder.dim
    return s
