"""健康检查与连接器元数据。"""

import json

from fastapi import APIRouter, Request, Response

from src.connectors import list_connectors

router = APIRouter(tags=["system"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request):
    svc = request.app.state.svc
    checks = {}
    try:
        svc.docstore.client.admin.command("ping")
        checks["mongo"] = True
    except Exception:  # noqa: BLE001
        checks["mongo"] = False
    try:
        checks["redis"] = bool(svc.cache.redis.ping())
    except Exception:  # noqa: BLE001
        checks["redis"] = False
    try:
        from kafka.admin import KafkaAdminClient
        KafkaAdminClient(bootstrap_servers=svc.env["KAFKA_BOOTSTRAP"], request_timeout_ms=3000).close()
        checks["kafka"] = True
    except Exception:  # noqa: BLE001
        checks["kafka"] = False
    ready = all(checks.values())
    return Response(content=json.dumps({"ready": ready, "checks": checks}, ensure_ascii=False),
                    status_code=200 if ready else 503, media_type="application/json")


@router.get("/v1/connectors")
def connectors():
    return {"connectors": list_connectors()}
