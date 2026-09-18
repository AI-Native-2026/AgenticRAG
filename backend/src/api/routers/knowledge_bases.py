"""知识库路由。"""

from fastapi import APIRouter, Request

from src.api.deps import AppError, get_bearer
from src.api.schemas import KBCreate, KBUpdate

router = APIRouter(prefix="/v1/knowledge-bases", tags=["knowledge-bases"])


@router.get("")
def list_kbs(request: Request):
    user = get_bearer(request)
    svc = request.app.state.svc
    tenant = None if user["role"] == "admin" else user["tenant"]
    items = svc.kb_store.list(tenant=tenant)
    for kb in items:
        kb["datasource_count"] = len(kb.get("datasource_ids", []))
        kb["chunk_count"] = sum(
            svc.docstore.col.count_documents({"datasource_id": d})
            for d in kb.get("datasource_ids", [])
        )
    return {"knowledge_bases": items}


@router.post("")
def create_kb(request: Request, body: KBCreate):
    user = get_bearer(request)
    svc = request.app.state.svc
    kb = svc.kb_store.create(body.name, user["tenant"], body.description,
                             body.slug, body.datasource_ids)
    for ds_id in body.datasource_ids:
        svc.datasource_store.update(ds_id, kb_id=kb["kb_id"])
    return kb


@router.get("/{kb_id}")
def get_kb(request: Request, kb_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    kb = svc.kb_store.get(kb_id)
    if not kb:
        raise AppError(404, "NOT_FOUND", f"知识库不存在：{kb_id}")
    if user["role"] != "admin" and kb["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权访问")
    kb["datasources"] = [svc.datasource_store.get(d) for d in kb.get("datasource_ids", [])]
    return kb


@router.patch("/{kb_id}")
def update_kb(request: Request, kb_id: str, body: KBUpdate):
    user = get_bearer(request)
    svc = request.app.state.svc
    kb = svc.kb_store.get(kb_id)
    if not kb:
        raise AppError(404, "NOT_FOUND", f"知识库不存在：{kb_id}")
    if user["role"] != "admin" and kb["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权操作")
    fields = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.datasource_ids is not None:
        fields["datasource_ids"] = body.datasource_ids
    if fields:
        svc.kb_store.update(kb_id, **fields)
    return svc.kb_store.get(kb_id)


@router.delete("/{kb_id}")
def delete_kb(request: Request, kb_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    kb = svc.kb_store.get(kb_id)
    if not kb:
        raise AppError(404, "NOT_FOUND", f"知识库不存在：{kb_id}")
    if user["role"] != "admin" and kb["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权操作")
    svc.kb_store.delete(kb_id)
    return {"deleted": True}
