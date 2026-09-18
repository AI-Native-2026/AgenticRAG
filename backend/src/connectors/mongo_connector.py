"""MongoDB 连接器。

- discover/describe：列出集合与字段样例
- read：按集合读取文档为 RawDocument（支持按 _id / 时间字段增量）
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.connectors.base import (
    BaseConnector, ConnectorError, RawDocument, ResourceMeta, SchemaInfo, register,
)


@register("mongodb")
@register("mongo")
class MongoConnector(BaseConnector):
    type = "database"
    subtype = "mongodb"
    capabilities = ("discover", "read", "describe")

    def __init__(self, datasource, credentials=None):
        super().__init__(datasource, credentials)
        self._client = None

    def _uri(self) -> str:
        return (self.config.get("uri")
                or f"mongodb://{self.config.get('host', 'localhost')}:{self.config.get('port', 27017)}")

    @property
    def client(self):
        if self._client is None:
            import pymongo
            self._client = pymongo.MongoClient(self._uri(), serverSelectionTimeoutMS=5000)
        return self._client

    @property
    def db(self):
        return self.client[self.config.get("database", "test")]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def test_connection(self) -> Tuple[bool, str]:
        try:
            self.client.admin.command("ping")
            return True, "连接成功（MongoDB）"
        except Exception as e:  # noqa: BLE001
            return False, f"连接失败：{type(e).__name__}: {e}"

    def discover(self) -> List[ResourceMeta]:
        allow = self.config.get("collections") or []
        names = self.db.list_collection_names()
        if allow:
            names = [n for n in names if n in set(allow)]
        out = []
        for n in sorted(names):
            try:
                rows = self.db[n].estimated_document_count()
            except Exception:  # noqa: BLE001
                rows = 0
            out.append(ResourceMeta(name=n, kind="collection", rows=rows))
        return out

    def describe(self, resource: str) -> SchemaInfo:
        sample = list(self.db[resource].find().limit(5))
        for d in sample:
            d.pop("_id", None)
        cols = [{"name": k, "type": type(v).__name__} for k, v in (sample[0].items() if sample else [])]
        return SchemaInfo(name=resource, columns=cols, sample_rows=sample,
                          row_count=self.db[resource].estimated_document_count())

    def preview(self, resource: Optional[str] = None, limit: int = 10,
                max_chars: int = 2000) -> List[RawDocument]:
        """预览（列名感知脱敏）。"""
        from src.config import get_env
        from src.connectors.masking import mask_row, row_to_text

        env = get_env()
        mask_on = bool(env.get("PII_MASK_ENABLED", True))
        pats = env.get("PII_MASK_COLUMNS")
        collections = [resource] if resource else [m.name for m in self.discover()]
        out: List[RawDocument] = []
        for coll in collections:
            for doc in self.db[coll].find().limit(limit):
                key = str(doc.pop("_id", ""))
                row = mask_row(doc, pats) if mask_on else doc
                out.append(RawDocument(
                    ref=f"{coll}:{key}", text=row_to_text(row)[:max_chars],
                    title=f"{coll} #{key}",
                    metadata={"source_type": "database", "datasource_id": self.ds_id,
                              "collection": coll, "modality": "table", "masked": mask_on},
                ))
                if len(out) >= limit:
                    return out
        return out

    def read(self, resource: Optional[str] = None, watermark: Any = None,
             limit: Optional[int] = None) -> Iterator[RawDocument]:
        collections = [resource] if resource else [m.name for m in self.discover()]
        wm_field = self.config.get("watermark_field")
        for coll in collections:
            query: Dict[str, Any] = {}
            if wm_field and watermark is not None:
                query[wm_field] = {"$gt": watermark}
            cursor = self.db[coll].find(query)
            if limit:
                cursor = cursor.limit(limit)
            for doc in cursor:
                key = str(doc.pop("_id", ""))
                text = "\n".join(f"{k}: {v}" for k, v in doc.items())
                yield RawDocument(
                    ref=f"{coll}:{key}",
                    text=text,
                    title=f"{coll} #{key}",
                    metadata={
                        "source_type": "database",
                        "datasource_id": self.ds_id,
                        "collection": coll,
                        "row_id": key,
                        "doc_name": coll,
                        "doc_type": "mongo_doc",
                        "page": 1,
                    },
                )
