"""连接器驱动的同步服务。

把任意连接器产出的 RawDocument 走完整流水线：
  读取 → 统一文档模型 → 去重/版本 → 切分 → 批量 embedding(缓存) → 写 docstore/向量库
并记录：任务进度、增量水位线、表结构、血缘。

同时用于：
  - 文件目录/上传 同步
  - 数据库同步（全量 / 增量）
  - Web 抓取同步
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.connectors.base import BaseConnector, RawDocument, create_connector
from src.ingestion.chunker import Chunker
from src.ingestion.dedup import DocDedup
from src.storage.crypto import decrypt
from src.storage.docstore import MongoDocStore, md5
from src.storage.index_store import MongoIndexStore
from src.storage.job_store import JobStore
from src.storage.schema_store import SchemaStore
from src.storage.sync_state import SyncStateStore
from src.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


def ref_doc_id_of(ds_id: str, ref: str) -> str:
    return "doc-" + md5(f"{ds_id}:{ref}")[:16]


class SyncService:
    """数据源 → 索引 的同步编排。"""

    def __init__(
        self,
        embed_model,
        docstore: MongoDocStore,
        vector_store: ChromaVectorStore,
        index_store: MongoIndexStore,
        cache=None,
        job_store: Optional[JobStore] = None,
        sync_state: Optional[SyncStateStore] = None,
        schema_store: Optional[SchemaStore] = None,
        lineage=None,
    ):
        self.embed_model = embed_model
        self.docstore = docstore
        self.vector_store = vector_store
        self.index_store = index_store
        self.cache = cache
        self.jobs = job_store or JobStore()
        self.sync_state = sync_state or SyncStateStore()
        self.schemas = schema_store or SchemaStore()
        self.lineage = lineage
        self.dedup = DocDedup()
        self.chunker = Chunker()

    # ---------- 连接器 ----------

    @staticmethod
    def build_connector(datasource: Dict[str, Any], credentials: Optional[Dict[str, str]] = None) -> BaseConnector:
        if credentials is None:
            creds = datasource.get("credentials") or {}
            credentials = {k: decrypt(v) for k, v in creds.items()}
        return create_connector(datasource, credentials)

    # ---------- 表结构抽取 ----------

    def extract_schema(self, datasource: Dict[str, Any], connector: Optional[BaseConnector] = None) -> int:
        connector = connector or self.build_connector(datasource)
        if not connector.supports("describe"):
            return 0
        count = 0
        for meta in connector.discover():
            try:
                info = connector.describe(meta.name)
                self.schemas.upsert(
                    datasource_id=datasource["ds_id"],
                    table=meta.name,
                    tenant=datasource.get("tenant", "default"),
                    columns=info.columns,
                    ddl=info.ddl,
                    sample_rows=_jsonable(info.sample_rows),
                    row_count=info.row_count,
                    description=info.description,
                )
                count += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("describe %s 失败: %s", meta.name, e)
        return count

    # ---------- 同步 ----------

    def sync_datasource(self, datasource: Dict[str, Any], mode: str = "full",
                        limit: Optional[int] = None, job_id: Optional[str] = None,
                        connector: Optional[BaseConnector] = None) -> Dict[str, Any]:
        ds_id = datasource["ds_id"]
        tenant = datasource.get("tenant", "default")
        connector = connector or self.build_connector(datasource)

        if job_id is None:
            job = self.jobs.create(ds_id, tenant, mode=mode)
            job_id = job["job_id"]

        stats = {"total": 0, "insert": 0, "update": 0, "skip": 0, "failed": 0,
                 "chunks": 0, "resources": 0}
        try:
            resources = connector.discover()
            self.jobs.start(job_id, total=len(resources))
            # 抽取表结构（仅数据库类，供 Text-to-SQL 与 Schema 树）
            if datasource.get("type") == "database":
                try:
                    self.extract_schema(datasource, connector)
                except Exception as e:  # noqa: BLE001
                    logger.warning("schema 抽取失败: %s", e)

            processed = 0
            for meta in resources:
                watermark = None
                if mode == "incremental" and connector.supports("read"):
                    watermark = self.sync_state.get_watermark(ds_id, meta.name)
                max_wm = watermark
                try:
                    for raw in connector.read(resource=meta.name, watermark=watermark, limit=limit):
                        self._ingest_raw(datasource, raw, stats)
                        stats["total"] += 1
                        wm_val = self._watermark_value(datasource, raw)
                        if wm_val is not None:
                            max_wm = wm_val
                except Exception as e:  # noqa: BLE001
                    stats["failed"] += 1
                    logger.error("资源 %s 同步失败: %s", meta.name, e)
                stats["resources"] += 1
                processed += 1
                if mode == "incremental":
                    self.sync_state.set(ds_id, meta.name, tenant, max_wm,
                                        rows_synced=stats["total"])
                self.jobs.progress(job_id, processed, total=len(resources),
                                   chunks=stats["chunks"], skipped=stats["skip"],
                                   failed=stats["failed"])

            self._write_index_meta()
            self.jobs.finish(job_id, status="success", **stats)
        except Exception as e:  # noqa: BLE001
            logger.exception("同步失败")
            self.jobs.finish(job_id, status="failed", error=f"{type(e).__name__}: {e}", **stats)
            raise
        finally:
            connector.close()

        # 更新数据源统计
        from src.storage.datasource_store import DatasourceStore
        try:
            DatasourceStore().set_status(ds_id, "ready", last_sync_at=time.time(),
                                         chunk_count=self._ds_chunk_count(ds_id),
                                         resource_count=stats["resources"])
        except Exception:  # noqa: BLE001
            pass
        return {"job_id": job_id, **stats}

    # ---------- 单条文档入库 ----------

    def _ingest_raw(self, datasource: Dict[str, Any], raw: RawDocument, stats: Dict[str, int]) -> None:
        ds_id = datasource["ds_id"]
        tenant = datasource.get("tenant", "default")
        ref_doc_id = ref_doc_id_of(ds_id, raw.ref)
        text_hash = md5(raw.text)

        action, version = self.dedup.decide(ref_doc_id, text_hash)
        if action == "skip":
            stats["skip"] += 1
            return

        doc = {
            "ref_doc_id": ref_doc_id,
            "doc_name": raw.metadata.get("doc_name") or raw.title or raw.ref,
            "tenant": tenant,
            "doc_type": raw.metadata.get("doc_type", "text"),
            "source_type": raw.metadata.get("source_type", datasource.get("type", "file")),
            "datasource_id": ds_id,
            "text": raw.text,
            "metadata": {k: v for k, v in raw.metadata.items()
                         if k not in ("source_type", "datasource_id", "doc_name", "doc_type")},
        }
        nodes = self.chunker.recursive_split(doc, doc_version=version)
        if not nodes:
            return

        if action == "update":
            self.docstore.delete_by_ref_doc(ref_doc_id)
            self.vector_store.delete_by_ref_doc(ref_doc_id)
            if self.cache:
                self.cache.invalidate(ref_doc_id)

        self.docstore.put_nodes(nodes)
        embeddings = self._embed_texts([n["text"] for n in nodes])
        self.vector_store.add_nodes(nodes, embeddings)
        self.dedup.save_record(ref_doc_id, text_hash, version, len(nodes))

        if self.lineage:
            try:
                self.lineage.record_doc_nodes(ref_doc_id, [n["node_id"] for n in nodes], version)
            except Exception:  # noqa: BLE001
                pass

        stats[action] += 1
        stats["chunks"] += len(nodes)

    # ---------- embedding ----------

    def _embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        results: List[Optional[List[float]]] = []
        pending_texts: List[str] = []
        pending_idx: List[int] = []
        for i, text in enumerate(texts):
            cached = self.cache.get_embedding(text) if self.cache else None
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                pending_texts.append(text)
                pending_idx.append(i)
        if pending_texts:
            for start in range(0, len(pending_texts), batch_size):
                batch = pending_texts[start:start + batch_size]
                vecs = self.embed_model.get_text_embedding_batch(batch)
                for local_i, vec in enumerate(vecs):
                    gi = pending_idx[start + local_i]
                    results[gi] = vec
                    if self.cache:
                        self.cache.set_embedding(pending_texts[start + local_i], vec)
        return results

    # ---------- 辅助 ----------

    def _watermark_value(self, datasource: Dict[str, Any], raw: RawDocument):
        wm_col = (datasource.get("config") or {}).get("watermark_column")
        if not wm_col:
            return None
        # 从行文本里粗略提取（同步场景通常用 row_id / 时间字段）
        return raw.metadata.get("watermark")

    def _ds_chunk_count(self, ds_id: str) -> int:
        try:
            return self.docstore.col.count_documents({"datasource_id": ds_id})
        except Exception:  # noqa: BLE001
            return 0

    def _write_index_meta(self) -> None:
        from src.config import get_env
        env = get_env()
        self.index_store.put_index({
            "index_name": "vector_main",
            "index_type": "vector",
            "node_ids": [],
            "embedding_model": env.get("EMBED_MODEL_NAME", "bge"),
            "embed_dim": int(env["EMBED_DIM"]),
            "extra": {"vector_count": self.vector_store.count(), "run_at": time.time()},
        })


def _jsonable(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        out.append({k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
                    for k, v in r.items()})
    return out
