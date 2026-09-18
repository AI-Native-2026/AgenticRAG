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
    qm = svc.quota
    tenants = []
    for t in qm.list_tenants():
        defaults = qm.get_tenant(t["_id"])
        merged = {**defaults, **t}
        merged["_id"] = str(merged.get("_id"))
        usage = Metering().daily_usage(tenant=merged["_id"], days=1)
        merged["used_tokens_today"] = usage["total_prompt"] + usage["total_completion"]
        merged["stored_nodes"] = svc.docstore.col.count_documents({"tenant": merged["_id"]})
        tenants.append(merged)
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


@router.get("/metrics/timeseries")
def metrics_timeseries(request: Request, days: int = 7, bucket: str = "day"):
    """按时间桶聚合事件，供时序图表使用。bucket = hour | day。"""
    user = get_bearer(request)
    require_admin(user)
    from datetime import datetime, timedelta
    import statistics

    events = get_sink().read_all(days=days)
    fmt = "%Y-%m-%d %H:00" if bucket == "hour" else "%Y-%m-%d"
    now = datetime.now()
    if bucket == "hour":
        buckets = [(now - timedelta(hours=h)).strftime(fmt) for h in range(days * 24 - 1, -1, -1)]
    else:
        buckets = [(now - timedelta(days=d)).strftime(fmt) for d in range(days - 1, -1, -1)]
    index = {b: i for i, b in enumerate(buckets)}

    req = [0] * len(buckets)
    tool = [0] * len(buckets)
    tokens = [0] * len(buckets)
    lat_gen: list[list[float]] = [[] for _ in buckets]
    lat_ret: list[list[float]] = [[] for _ in buckets]

    for e in events:
        ts = e.get("ts")
        if not ts:
            continue
        key = datetime.fromtimestamp(ts).strftime(fmt)
        i = index.get(key)
        if i is None:
            continue
        et = e.get("event_type")
        if et == "request_start":
            req[i] += 1
        elif et == "tool_call":
            tool[i] += 1
        elif et == "generate":
            tokens[i] += int(e.get("total_tokens") or e.get("prompt_tokens") or 0)
            if e.get("duration_ms"):
                lat_gen[i].append(e["duration_ms"])
        elif et == "retrieval" and e.get("duration_ms"):
            lat_ret[i].append(e["duration_ms"])

    def pct(vals, p):
        if not vals:
            return 0
        if len(vals) == 1:
            return round(vals[0], 1)
        q = statistics.quantiles(vals, n=100)
        return round(q[min(p, 99) - 1], 1)

    return {
        "bucket": bucket,
        "buckets": buckets,
        "series": {
            "requests": req,
            "tool_calls": tool,
            "tokens": tokens,
            "latency_p50": [pct(v, 50) for v in lat_gen],
            "latency_p95": [pct(v, 95) for v in lat_gen],
            "retrieval_p95": [pct(v, 95) for v in lat_ret],
        },
    }


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
