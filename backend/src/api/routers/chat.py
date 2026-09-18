"""对话路由（流式 SSE + 非流式）。"""

import json
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.api.deps import AppError, get_bearer
from src.api.schemas import ChatRequest, ChatResponse
from src.api.sse import sse_event
from src.observability.events import make_event, new_request_id
from src.observability.sink import get_sink

router = APIRouter(prefix="/v1", tags=["chat"])


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
        set_ctx(role=user["role"], request_id=request_id, tenant=user["tenant"])
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
        title = (d.get("first_user") or "新会话")
        out.append({"session_id": d["_id"], "last": d["last"], "messages": d["count"],
                    "title": title[:40]})
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
