"""文档路由：提交入库 / 列表 / chunk 明细 / 删除。"""

import hashlib
import time
from typing import Optional

from fastapi import APIRouter, Request

from src.api.deps import AppError, get_bearer
from src.api.schemas import DocSubmitRequest, DocSubmitResponse

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("", response_model=DocSubmitResponse)
def submit_docs(request: Request, body: DocSubmitRequest):
    user = get_bearer(request)
    svc = request.app.state.svc
    # 租户绑定：非 admin 只能用登录租户，防止越权写入
    tenant = body.tenant if (user["role"] == "admin" and body.tenant) else user["tenant"]

    if body.idempotency_key:
        key = f"idem:{body.idempotency_key}"
        if not svc.cache.redis.set(key, "1", nx=True, ex=3600):
            return DocSubmitResponse(accepted=len(body.docs), request_id="duplicate-skip")

    docs = [
        {
            "ref_doc_id": "doc-" + hashlib.md5(
                f"{tenant}:{d.doc_name}:{int(time.time())}".encode()).hexdigest()[:16],
            "doc_name": d.doc_name,
            "tenant": tenant,
            "doc_type": d.doc_type,
            "source_type": "file",
            "datasource_id": body.datasource_id,
            "text": d.text,
        }
        for d in body.docs
    ]
    svc.mark_bm25_dirty()
    from src.ingestion.producer import DocumentProducer
    n = DocumentProducer().publish_docs(docs, request_id=body.idempotency_key or "api")
    return DocSubmitResponse(accepted=n, request_id=body.idempotency_key or "api")


@router.get("")
def list_documents(request: Request, tenant: Optional[str] = None,
                   datasource_id: Optional[str] = None, limit: int = 200):
    user = get_bearer(request)
    svc = request.app.state.svc
    scope = tenant if (user["role"] == "admin" and tenant) else user["tenant"]
    match = {}
    if scope:
        match["tenant"] = scope
    if datasource_id:
        match["datasource_id"] = datasource_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$ref_doc_id",
            "doc_name": {"$first": "$doc_name"},
            "doc_type": {"$first": "$doc_type"},
            "source_type": {"$first": "$source_type"},
            "datasource_id": {"$first": "$datasource_id"},
            "doc_version": {"$max": "$doc_version"},
            "chunks": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}}, {"$limit": limit},
    ]
    docs = [{"ref_doc_id": d["_id"], "doc_name": d.get("doc_name"),
             "doc_type": d.get("doc_type"), "source_type": d.get("source_type"),
             "datasource_id": d.get("datasource_id"),
             "doc_version": d.get("doc_version"), "chunks": d["chunks"]}
            for d in svc.docstore.col.aggregate(pipeline)]
    return {"documents": docs, "count": len(docs)}


@router.get("/{ref_doc_id}")
def get_document(request: Request, ref_doc_id: str, limit: int = 200, mask: bool = True):
    user = get_bearer(request)
    svc = request.app.state.svc
    nodes = svc.docstore.get_nodes_by_ref_doc(ref_doc_id)
    if not nodes:
        raise AppError(404, "NOT_FOUND", f"文档不存在：{ref_doc_id}")
    if user["role"] != "admin" and nodes[0].get("tenant") != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权访问")
    nodes.sort(key=lambda n: n.get("chunk_idx", 0))

    env = svc.env
    mask_on = mask and bool(env.get("PII_MASK_ENABLED", True))
    extra = env.get("PII_MASK_EXTRA")
    chunks = []
    for n in nodes[:limit]:
        text = n["text"]
        meta = n.get("metadata", {})
        if mask_on:
            from src.connectors.masking import mask_any, mask_text
            text = mask_text(text, extra)
            meta = mask_any(meta, extra)
        chunks.append({
            "node_id": n["node_id"], "chunk_idx": n.get("chunk_idx"),
            "text": text, "metadata": meta,
            "datasource_id": n.get("datasource_id"),
            "source_type": n.get("source_type"),
        })
    return {
        "ref_doc_id": ref_doc_id,
        "doc_name": nodes[0].get("doc_name"),
        "doc_version": nodes[0].get("doc_version"),
        "masked": mask_on,
        "chunks": chunks,
    }


@router.delete("/{ref_doc_id}")
def delete_document(request: Request, ref_doc_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    nodes = svc.docstore.get_nodes_by_ref_doc(ref_doc_id)
    if not nodes:
        raise AppError(404, "NOT_FOUND", f"文档不存在：{ref_doc_id}")
    if user["role"] != "admin" and nodes[0].get("tenant") != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权操作")
    svc.docstore.delete_by_ref_doc(ref_doc_id)
    svc.vector_store.delete_by_ref_doc(ref_doc_id)
    svc.cache.invalidate(ref_doc_id)
    svc.mark_bm25_dirty()
    return {"deleted": True, "ref_doc_id": ref_doc_id, "chunks": len(nodes)}
