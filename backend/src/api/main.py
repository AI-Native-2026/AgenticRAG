"""FastAPI 应用入口。

  POST /v1/auth/login              登录拿 JWT
  GET  /healthz /readyz            存活/就绪探针
  POST /v1/chat                    Agent 对话（SSE 流式）
  GET  /v1/datasources            数据源 CRUD / 测试 / 发现 / Schema / 同步
  GET  /v1/jobs                    入库任务
  GET  /v1/knowledge-bases         知识库
  GET  /v1/documents               文档与 chunk
  POST /v1/retrieval/search        检索调试
  GET  /v1/metrics /audit /alerts /tenants
"""

import json
import logging
from contextlib import asynccontextmanager

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps import AppError
from src.api.routers import api_router
from src.api.services import AppServices
from src.config import get_env
from src.observability.events import new_request_id

logger = logging.getLogger("api")
ENV = get_env()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动服务，构建模型/索引…")
    app.state.svc = AppServices()
    logger.info("服务就绪")
    yield


app = FastAPI(title="Agentic RAG 知识中台", version="3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ENV["CORS_ORIGINS"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return Response(
        content=json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False),
        status_code=exc.status_code, media_type="application/json",
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    rid = new_request_id()
    logger.error("unhandled error request_id=%s err=%s", rid, exc, exc_info=True)
    return Response(
        content=json.dumps({"code": "INTERNAL", "message": "服务器内部错误",
                            "request_id": rid}, ensure_ascii=False),
        status_code=500, media_type="application/json",
    )


app.include_router(api_router)

# 可选：若前端已构建（frontend/dist），由后端同端口托管，实现单端口部署
_FRONTEND_DIST = Path(ENV["PROJECT_ROOT"]).parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="ui")
    logger.info("已挂载前端静态资源：%s", _FRONTEND_DIST)
