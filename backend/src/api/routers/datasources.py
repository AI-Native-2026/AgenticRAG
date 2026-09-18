"""数据源路由：CRUD / 测试连接 / 发现资源 / Schema / 预览 / 同步。"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Request

from src.api.deps import AppError, get_bearer, require_admin
from src.api.schemas import DatasourceCreate, DatasourceUpdate, SyncRequest, TestConnectionRequest
from src.connectors import create_connector

router = APIRouter(prefix="/v1/datasources", tags=["datasources"])


def _owned(svc, ds_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    ds = svc.datasource_store.get(ds_id)
    if not ds:
        raise AppError(404, "NOT_FOUND", f"数据源不存在：{ds_id}")
    if user["role"] != "admin" and ds["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权访问其他租户的数据源")
    return ds


@router.get("")
def list_datasources(request: Request):
    user = get_bearer(request)
    svc = request.app.state.svc
    tenant = None if user["role"] == "admin" else user["tenant"]
    return {"datasources": svc.datasource_store.list(tenant=tenant)}


@router.post("")
def create_datasource(request: Request, body: DatasourceCreate):
    user = get_bearer(request)
    svc = request.app.state.svc
    ds = svc.datasource_store.create(
        name=body.name, type=body.type, subtype=body.subtype,
        tenant=user["tenant"], config=body.config,
        credentials=body.credentials, kb_id=body.kb_id,
    )
    if body.kb_id:
        svc.kb_store.add_datasource(body.kb_id, ds["ds_id"])
    return ds


@router.get("/{ds_id}")
def get_datasource(request: Request, ds_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    ds = _owned(svc, ds_id, user)
    ds["sync_state"] = svc.sync_state.list(ds_id)
    return ds


@router.patch("/{ds_id}")
def update_datasource(request: Request, ds_id: str, body: DatasourceUpdate):
    user = get_bearer(request)
    svc = request.app.state.svc
    _owned(svc, ds_id, user)
    fields: Dict[str, Any] = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.config is not None:
        fields["config"] = body.config
    if body.kb_id is not None:
        fields["kb_id"] = body.kb_id
    if fields:
        svc.datasource_store.update(ds_id, **fields)
    if body.credentials:
        svc.datasource_store.set_credentials(ds_id, body.credentials)
    return svc.datasource_store.get(ds_id)


@router.delete("/{ds_id}")
def delete_datasource(request: Request, ds_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    _owned(svc, ds_id, user)
    # 清理该数据源的向量与文档
    for node in svc.docstore.col.find({"datasource_id": ds_id}, {"ref_doc_id": 1}):
        ref = node.get("ref_doc_id")
        if ref:
            svc.vector_store.delete_by_ref_doc(ref)
            svc.cache.invalidate(ref)
    svc.docstore.col.delete_many({"datasource_id": ds_id})
    svc.schema_store.clear(ds_id)
    svc.sync_state.col.delete_many({"datasource_id": ds_id})
    svc.datasource_store.delete(ds_id)
    svc.mark_bm25_dirty()
    return {"deleted": True, "ds_id": ds_id}


@router.post("/test")
def test_connection(request: Request, body: TestConnectionRequest):
    """在创建前测试连接（无需落库）。"""
    get_bearer(request)
    ds = {"ds_id": "test", "name": "test", "tenant": "test",
          "subtype": body.subtype, "config": body.config}
    try:
        conn = create_connector(ds, body.credentials)
        ok, msg = conn.test_connection()
        conn.close()
        return {"ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


@router.post("/{ds_id}/test")
def test_saved(request: Request, ds_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    _owned(svc, ds_id, user)
    raw = svc.datasource_store.get_raw(ds_id)
    try:
        conn = svc.sync_service.build_connector(raw)
        ok, msg = conn.test_connection()
        conn.close()
        svc.datasource_store.set_status(ds_id, "connected" if ok else "error")
        return {"ok": ok, "message": msg}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


@router.get("/{ds_id}/resources")
def discover(request: Request, ds_id: str, page: int = 1, page_size: int = 10, q: str = ""):
    """列出资源（文件/表），分页返回，避免大目录一次性加载。"""
    user = get_bearer(request)
    svc = request.app.state.svc
    raw = svc.datasource_store.get_raw(ds_id)
    _owned(svc, ds_id, user)
    conn = svc.sync_service.build_connector(raw)
    try:
        items = conn.discover()
        if q:
            ql = q.lower()
            items = [r for r in items if ql in r.name.lower()]
        total = len(items)
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        start = (page - 1) * page_size
        page_items = items[start:start + page_size]
        return {
            "items": [{"name": r.name, "kind": r.kind, "size": r.extra.get("size", r.rows),
                       "suffix": r.extra.get("suffix", ""), "columns": r.columns} for r in page_items],
            "total": total, "page": page, "page_size": page_size,
        }
    finally:
        conn.close()


@router.get("/{ds_id}/files")
def list_files(request: Request, ds_id: str, page: int = 1, page_size: int = 10, q: str = ""):
    """文件目录分页列表（名称 / 大小 / 类型）。"""
    user = get_bearer(request)
    svc = request.app.state.svc
    raw = svc.datasource_store.get_raw(ds_id)
    _owned(svc, ds_id, user)
    if raw.get("type") != "file":
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    conn = svc.sync_service.build_connector(raw)
    try:
        from pathlib import Path as _P
        files = conn.discover()
        if q:
            ql = q.lower()
            files = [f for f in files if ql in f.name.lower()]
        total = len(files)
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        start = (page - 1) * page_size
        items = []
        for f in files[start:start + page_size]:
            p = _P(f.name)
            items.append({"path": f.name, "name": p.name,
                          "suffix": f.extra.get("suffix", p.suffix.lower()),
                          "size": f.extra.get("size", f.rows)})
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        conn.close()


@router.get("/{ds_id}/schema")
def schema(request: Request, ds_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    _owned(svc, ds_id, user)
    return {"tables": svc.schema_store.list(ds_id)}


@router.get("/{ds_id}/preview")
def preview(request: Request, ds_id: str, resource: Optional[str] = None, limit: int = 10,
            mask: bool = True):
    """轻量预览：限制条数与单条字符数，避免大文件占用资源；默认脱敏。"""
    user = get_bearer(request)
    svc = request.app.state.svc
    raw = svc.datasource_store.get_raw(ds_id)
    _owned(svc, ds_id, user)
    env = svc.env
    limit = max(1, min(limit, 50))
    mask_on = mask and bool(env.get("PII_MASK_ENABLED", True))
    conn = svc.sync_service.build_connector(raw)
    try:
        docs = conn.preview(resource=resource, limit=limit,
                            max_chars=int(env.get("PREVIEW_MAX_CHARS", 2000)))
        out = []
        for d in docs:
            text = d.text
            meta = d.metadata
            if mask_on:
                from src.connectors.masking import mask_any, mask_text
                text = mask_text(text, env.get("PII_MASK_EXTRA"))
                meta = mask_any(meta, env.get("PII_MASK_EXTRA"))
            out.append({"ref": d.ref, "title": d.title, "text": text, "metadata": meta})
        return {"preview": out, "masked": mask_on}
    finally:
        conn.close()


def _run_sync(svc, ds_id: str, mode: str, limit: Optional[int], job_id: Optional[str] = None) -> None:
    raw = svc.datasource_store.get_raw(ds_id)
    svc.datasource_store.set_status(ds_id, "syncing")
    try:
        svc.sync_service.sync_datasource(raw, mode=mode, limit=limit, job_id=job_id)
    except Exception:  # noqa: BLE001
        svc.datasource_store.set_status(ds_id, "error")
    finally:
        svc.mark_bm25_dirty()


@router.post("/{ds_id}/sync")
def sync(request: Request, ds_id: str, body: SyncRequest, background: BackgroundTasks):
    user = get_bearer(request)
    svc = request.app.state.svc
    _owned(svc, ds_id, user)
    job = svc.job_store.create(ds_id, user["tenant"], mode=body.mode)
    background.add_task(_run_sync, svc, ds_id, body.mode, body.limit, job["job_id"])
    return {"job_id": job["job_id"], "status": "pending"}
