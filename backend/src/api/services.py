"""应用组合根（Composition Root）。

一次性构建重量级组件（模型 / 存储 / 检索 / 工具 / 同步服务），全局共享；
每个请求只构建轻量 Agent。
"""

import logging
import threading
from typing import Any, Dict

from src.agent.agent import AgenticRAG
from src.agent.tools import RAGTools
from src.config import get_env
from src.ingestion.sync import SyncService
from src.llm.gateway import LLMGateway, build_embed_model
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.rerank import Reranker
from src.storage.cache import CacheClient
from src.storage.datasource_store import DatasourceStore
from src.storage.docstore import MongoDocStore
from src.storage.index_store import MongoIndexStore
from src.storage.job_store import JobStore
from src.storage.kb_store import KnowledgeBaseStore
from src.storage.lineage import LineageStore
from src.storage.quota import QuotaManager
from src.storage.schema_store import SchemaStore
from src.storage.sync_state import SyncStateStore
from src.storage.vector_store import ChromaVectorStore

logger = logging.getLogger("api")


class AppServices:
    """一次性构建、全局共享的重量级服务。"""

    def __init__(self):
        self.env = get_env()
        from src.llm.multimodal import get_embedder

        self.embedder = get_embedder()
        self.embed_model = getattr(self.embedder, "model", None)
        self.docstore = MongoDocStore()
        self.vector_store = ChromaVectorStore()
        self.index_store = MongoIndexStore()
        self.cache = CacheClient()
        self.quota = QuotaManager()

        self.datasource_store = DatasourceStore()
        self.job_store = JobStore()
        self.kb_store = KnowledgeBaseStore()
        self.schema_store = SchemaStore()
        self.sync_state = SyncStateStore()
        self.lineage = LineageStore()

        self.hybrid = HybridRetriever(vector_store=self.vector_store, embedder=self.embedder)
        self._bm25_lock = threading.Lock()
        self.hybrid.set_node_provider(self.docstore.get_all_nodes)
        self.rebuild_bm25()

        self.reranker = Reranker(backend=self.env.get("RERANK_BACKEND", "cross_encoder"))
        self.tools = RAGTools(self.hybrid, self.reranker,
                              datasource_store=self.datasource_store,
                              schema_store=self.schema_store)
        self.gateway = LLMGateway()
        self.rag = AgenticRAG(self.tools.build_tools(), self.gateway.build_llm())

        self.sync_service = SyncService(
            embedder=self.embedder,
            docstore=self.docstore,
            vector_store=self.vector_store,
            index_store=self.index_store,
            cache=self.cache,
            job_store=self.job_store,
            sync_state=self.sync_state,
            schema_store=self.schema_store,
            lineage=self.lineage,
        )

    def rebuild_bm25(self) -> None:
        """立即重建 BM25 索引（全量）。"""
        with self._bm25_lock:
            self.hybrid.build_bm25(self.docstore.get_all_nodes())

    def mark_bm25_dirty(self) -> None:
        """标记 BM25 过期，下次检索时惰性重建（避免批量写入时反复重建）。"""
        self.hybrid.mark_dirty()

    def stats(self) -> Dict[str, Any]:
        try:
            vector_count = self.vector_store.count()
        except Exception:  # noqa: BLE001
            vector_count = 0
        return {
            "documents": self.docstore.count(),
            "chunks": vector_count,
            "datasources": self.datasource_store.count(),
            "knowledge_bases": self.kb_store.count(),
        }
