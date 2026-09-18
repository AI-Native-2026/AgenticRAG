"""运维/管理路由：指标、审计、告警、租户配额。"""

from typing import Optional

from fastapi import APIRouter, Request

from src.api.deps import AppError, get_bearer, require_admin
from src.observability.metrics import aggregate, format_report
from src.observability.sink import get_sink
from src.storage.metering import Metering

router = APIRouter(prefix="/v1", tags=["admin"])


@router.get("/metrics")
def metrics(request: Request, days: int = 1):
    user = get_bearer(request)
    require_admin(user)
    svc = request.app.state.svc
    events = get_sink().read_all(days=days)
    report = aggregate(events, metering=Metering().daily_usage(days=days))
    report["kv_cache_hit_rate"] = svc.gateway.kv_cache_hit_rate
    report["stats"] = svc.stats()
    return {"report": report, "text": format_report(report)}


@router.get("/audit")
def audit(request: Request, limit: int = 100, tool: Optional[str] = None):
    user = get_bearer(request)
    require_admin(user)
    svc = request.app.state.svc
    q = {"tool": tool} if tool else {}
    items = list(svc.tools.audit.col.find(q).sort("ts", -1).limit(limit))
    for it in items:
        it["_id"] = str(it.get("_id"))
    return {"audit": items}


@router.get("/alerts")
def alerts(request: Request):
    user = get_bearer(request)
    require_admin(user)
    from src.observability.alerts import check, load_rules
    svc = request.app.state.svc
    events = get_sink().read_all(days=1)
    report = aggregate(events, metering=Metering().daily_usage(days=1))
    rules = load_rules()
    return {"alerts": check(report, rules), "rules": rules}


@router.get("/tenants")
def list_tenants(request: Request):
    user = get_bearer(request)
    require_admin(user)
    svc = request.app.state.svc
    tenants = svc.quota.list_tenants()
    for t in tenants:
        t["_id"] = str(t.get("_id"))
        usage = Metering().daily_usage(tenant=t.get("_id"), days=1)
        t["used_tokens_today"] = usage["total_prompt"] + usage["total_completion"]
        t["stored_nodes"] = svc.docstore.col.count_documents({"tenant": t.get("_id")})
    return {"tenants": tenants}


@router.post("/tenants")
def create_tenant(request: Request, body: dict):
    user = get_bearer(request)
    require_admin(user)
    tenant = body.get("tenant")
    if not tenant:
        raise AppError(400, "BAD_REQUEST", "缺少 tenant")
    from src.storage.quota import QuotaManager
    QuotaManager().create_tenant(
        tenant,
        quota_tokens_per_day=int(body.get("quota_tokens_per_day", 100000)),
        quota_storage_nodes=int(body.get("quota_storage_nodes", 10000)),
    )
    return {"created": True, "tenant": tenant}


@router.get("/dashboard/summary")
def dashboard_summary(request: Request):
    user = get_bearer(request)
    svc = request.app.state.svc
    tenant = None if user["role"] == "admin" else user["tenant"]
    counts = svc.job_store.count_by_status(tenant=tenant)
    events = get_sink().read_all(days=1)
    report = aggregate(events, metering=Metering().daily_usage(days=1))
    return {
        "stats": svc.stats(),
        "jobs": counts,
        "metrics": {
            "request_count": report.get("request_count", 0),
            "latency_p95_generate": report.get("latency_p95", {}).get("generate"),
            "tool_calls": report.get("tool_calls", {}),
            "total_tokens": report.get("total_tokens", 0),
        },
        "recent_jobs": svc.job_store.list(tenant=tenant, limit=6),
    }
