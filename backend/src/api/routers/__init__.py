"""API 路由聚合。"""

from fastapi import APIRouter

from src.api.routers import (
    admin, auth, chat, datasources, documents, eval as eval_router, health, jobs,
    knowledge_bases, retrieval,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(datasources.router)
api_router.include_router(jobs.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(documents.router)
api_router.include_router(retrieval.router)
api_router.include_router(eval_router.router)
api_router.include_router(admin.router)
