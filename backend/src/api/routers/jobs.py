"""入库任务路由。"""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request

from src.api.deps import AppError, get_bearer
from src.api.routers.datasources import _run_sync

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("")
def list_jobs(request: Request, status: Optional[str] = None,
              datasource_id: Optional[str] = None, limit: int = 100):
    user = get_bearer(request)
    svc = request.app.state.svc
    tenant = None if user["role"] == "admin" else user["tenant"]
    jobs = svc.job_store.list(tenant=tenant, datasource_id=datasource_id,
                              status=status, limit=limit)
    return {"jobs": jobs, "counts": svc.job_store.count_by_status(tenant=tenant)}


@router.get("/{job_id}")
def get_job(request: Request, job_id: str):
    user = get_bearer(request)
    svc = request.app.state.svc
    job = svc.job_store.get(job_id)
    if not job:
        raise AppError(404, "NOT_FOUND", f"任务不存在：{job_id}")
    if user["role"] != "admin" and job["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权访问")
    return job


@router.post("/{job_id}/retry")
def retry_job(request: Request, job_id: str, background: BackgroundTasks):
    user = get_bearer(request)
    svc = request.app.state.svc
    job = svc.job_store.get(job_id)
    if not job:
        raise AppError(404, "NOT_FOUND", f"任务不存在：{job_id}")
    if user["role"] != "admin" and job["tenant"] != user["tenant"]:
        raise AppError(403, "FORBIDDEN", "无权操作")
    new_job = svc.job_store.create(job["datasource_id"], job["tenant"], mode=job.get("mode", "full"))
    background.add_task(_run_sync, svc, job["datasource_id"], job.get("mode", "full"), None)
    return {"job_id": new_job["job_id"], "status": "pending"}
