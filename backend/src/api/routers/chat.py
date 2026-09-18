"""对话路由（流式 SSE + 非流式 + 图片问答）。"""

import json
import logging
import os
import tempfile
from typing import AsyncIterator

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.api.deps import AppError, get_bearer
from src.api.schemas import ChatRequest, ChatResponse
from src.api.sse import sse_event
from src.observability.events import make_event, new_request_id
from src.observability.sink import get_sink

router = APIRouter(prefix="/v1", tags=["chat"])
logger = logging.getLogger(__name__)


def _prepare(request: Request):
    user = get_bearer(request)
    svc = request.app.state.svc
    tenant = user["tenant"]
    if not svc.quota.check_token_quota(tenant):
        get_sink().record(make_event("quota_denied", request_id="n/a", tenant=tenant))
        raise AppError(429, "QUOTA_EXCEEDED", f"租户 {tenant} 今日 token 预算已用完")
    if not svc.gateway.rate_limiter.allow(tenant):
        raise AppError(429, "RATE_LIMITED", f"租户 {tenant} 请求过于频繁")
    return user, svc


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    user, svc = _prepare(request)
    request_id = new_request_id()
    agent = svc.rag.build_agent(role=user["role"], tenant=user["tenant"])

    if not body.stream:
        from src.agent.tools import clear_ctx, set_ctx
        set_ctx(role=user["role"], request_id=request_id, tenant=user["tenant"],
                kb_ids=body.kb_ids, datasource_ids=body.datasource_ids)
        try:
            result = await svc.rag.achat(agent, body.session_id, body.question, tenant=user["tenant"])
        finally:
            clear_ctx()
        return ChatResponse(answer=result["answer"], request_id=result["request_id"])

    async def gen() -> AsyncIterator[str]:
        yield sse_event("start", {"request_id": request_id})
        try:
            async for ev in svc.rag.achat_stream(
                agent, body.session_id, body.question,
                role=user["role"], tenant=user["tenant"], request_id=request_id,
                kb_ids=body.kb_ids, datasource_ids=body.datasource_ids,
            ):
                yield sse_event(ev["event"], ev["data"])
        except Exception as e:  # noqa: BLE001
            yield sse_event("error", {"message": f"{type(e).__name__}: {e}",
                                      "request_id": request_id})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions/{session_id}")
def session_history(session_id: str, request: Request):
    user = get_bearer(request)
    svc = request.app.state.svc
    return {"session_id": session_id, "messages": svc.rag.sessions.history(session_id, limit=100)}


@router.get("/sessions")
def list_sessions(request: Request):
    get_bearer(request)
    svc = request.app.state.svc
    col = svc.rag.sessions.col
    pipeline = [
        {"$sort": {"ts": 1}},
        {"$group": {
            "_id": "$session_id",
            "last": {"$max": "$ts"},
            "count": {"$sum": 1},
            "first_user": {"$first": {"$cond": [{"$eq": ["$role", "user"]}, "$content", "$$REMOVE"]}},
        }},
        {"$sort": {"last": -1}}, {"$limit": 50},
    ]
    out = []
    for d in col.aggregate(pipeline):
        stored = svc.rag.sessions.get_title(d["_id"])
        title = stored or (d.get("first_user") or "新会话")
        out.append({"session_id": d["_id"], "last": d["last"], "messages": d["count"],
                    "title": str(title)[:40]})
    return {"sessions": out}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    get_bearer(request)
    svc = request.app.state.svc
    n = svc.rag.sessions.clear(session_id)
    return {"deleted": n, "session_id": session_id}


@router.get("/sessions/{session_id}/memory")
def session_memory(session_id: str, request: Request):
    get_bearer(request)
    svc = request.app.state.svc
    stats = svc.rag.context.stats(session_id)
    rec = svc.rag.sessions.get_summary(session_id)
    stats["summary"] = rec.get("summary") if rec else None
    return stats


def _scope_where(svc, user, kb_ids: str, datasource_ids: str):
    where = {}
    if user["role"] != "admin":
        where["tenant"] = user["tenant"]
    union = set()
    for kid in [k for k in (kb_ids or "").split(",") if k]:
        kb = svc.kb_store.get(kid)
        if kb:
            union.update(kb.get("datasource_ids", []))
    ds = [d for d in (datasource_ids or "").split(",") if d]
    if union:
        where["datasource_id"] = {"$in": list(union)}
    elif ds:
        where["datasource_id"] = {"$in": ds}
    return where or None


@router.post("/chat/image")
async def chat_image(request: Request, file: UploadFile = File(...), question: str = Form(""),
                     session_id: str = Form("default"), kb_ids: str = Form(""),
                     datasource_ids: str = Form("")):
    """图片问答：上传图片 + 问题 → 结合图片 OCR 与知识库检索内容回答（尊重用户问题）。"""
    user, svc = _prepare(request)
    request_id = new_request_id()
    suffix = os.path.splitext(file.filename or "q.png")[1] or ".png"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(tmp, "wb") as f:
        f.write(await file.read())

    try:
        # 1) 图片 OCR（提取图中文字）
        ocr_text = ""
        try:
            from pathlib import Path as _P

            from src.connectors.media import ocr_image
            ocr_text = ocr_image(_P(tmp))
        except Exception:  # noqa: BLE001
            pass
        # 2) 以图检索相关内容
        where = _scope_where(svc, user, kb_ids, datasource_ids)
        hits = []
        try:
            emb = svc.embedder.embed_items([{"modality": "image", "media_path": tmp}])[0]
            hits = svc.vector_store.query(emb, top_k=6, where=where)
        except Exception:  # noqa: BLE001
            pass
        sources = [{
            "node_id": h["node_id"],
            "doc_name": (h.get("metadata") or {}).get("doc_name", ""),
            "modality": (h.get("metadata") or {}).get("modality", "text"),
            "score": round(float(h.get("score") or 0), 3),
        } for h in hits]

        ctx_lines = []
        if ocr_text:
            ctx_lines.append("【上传图片的 OCR 文本】\n" + ocr_text[:1500])
        for i, h in enumerate(hits[:5]):
            meta = h.get("metadata") or {}
            ctx_lines.append(
                f"[{i + 1}] 来源:{meta.get('doc_name', '')}（{meta.get('modality', 'text')}）\n"
                f"{h.get('text', '')[:600]}")
        context = "\n\n".join(ctx_lines) or "（未检索到相关内容）"

        q = question.strip() or "请描述这张图片的内容。"
        prompt = (
            "你是小K，企业的知识中台助手。用户上传了一张图片并提问。"
            "下面是系统针对该图片得到的信息（OCR 文本与知识库检索结果），请据此回答用户问题；"
            "若信息不足，如实说明。用中文、Markdown 排版，不要输出角色前缀。\n\n"
            f"{context}\n\n用户问题：{q}"
        )
        # 优先用视觉模型（Qwen2.5-VL）直接理解图片；失败则回退 OCR + 文本模型
        answer = ""
        if svc.env.get("VLM_CHAT_ENABLED", True):
            try:
                import asyncio

                from src.llm.vision import answer_image
                answer = await asyncio.to_thread(answer_image, tmp, q)
            except Exception as e:  # noqa: BLE001
                logger.warning("VLM 问答失败，回退文本模型: %s", e)
        if not answer:
            answer = str(await svc.rag.llm.acomplete(prompt))

        async def gen() -> AsyncIterator[str]:
            yield sse_event("start", {"request_id": request_id})
            if sources:
                yield sse_event("sources", {"items": sources})
            for i in range(0, len(answer), 24):
                yield sse_event("token", {"content": answer[i:i + 24]})
            yield sse_event("done", {"request_id": request_id})

        try:
            svc.rag.sessions.append(session_id, "user", f"[图片] {question}".strip())
            svc.rag.sessions.append(session_id, "assistant", answer)
        except Exception:  # noqa: BLE001
            pass
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
