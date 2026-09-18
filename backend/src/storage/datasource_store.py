"""数据源（Datasource）。

统一描述文件目录 / 数据库 / Web 三类接入源。
表：agentic_rag.datasources
  {_id: ds_id, ds_id, name, type, subtype, tenant, kb_id,
   config: {非敏感配置}, credentials: {加密凭证},
   status, resource_count, chunk_count, last_sync_at, created_at, updated_at}
"""

import time
import uuid
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env
from src.storage.mongo import get_client
from src.storage.crypto import decrypt, encrypt


class DatasourceStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = get_client(uri or env["MONGO_URI"])
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["datasources"]
        self.col.create_index("tenant")
        self.col.create_index("kb_id")

    def create(self, name: str, type: str, subtype: str, tenant: str,
               config: Optional[Dict[str, Any]] = None,
               credentials: Optional[Dict[str, str]] = None,
               kb_id: Optional[str] = None) -> Dict[str, Any]:
        ds_id = "ds-" + uuid.uuid4().hex[:12]
        enc = {k: encrypt(v) for k, v in (credentials or {}).items() if v is not None}
        doc = {
            "_id": ds_id,
            "ds_id": ds_id,
            "name": name,
            "type": type,          # file | database | web
            "subtype": subtype,    # directory | upload | mysql | postgresql | ...
            "tenant": tenant,
            "kb_id": kb_id,
            "config": config or {},
            "credentials": enc,
            "status": "created",
            "resource_count": 0,
            "chunk_count": 0,
            "last_sync_at": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.col.insert_one(doc)
        return self.public(doc)

    def get_raw(self, ds_id: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": ds_id})

    def get(self, ds_id: str) -> Optional[Dict[str, Any]]:
        doc = self.get_raw(ds_id)
        return self.public(doc) if doc else None

    def credentials(self, ds_id: str) -> Dict[str, str]:
        doc = self.get_raw(ds_id) or {}
        return {k: decrypt(v) for k, v in (doc.get("credentials") or {}).items()}

    def list(self, tenant: Optional[str] = None, kb_id: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if tenant:
            q["tenant"] = tenant
        if kb_id:
            q["kb_id"] = kb_id
        return [self.public(d) for d in self.col.find(q).sort("created_at", -1)]

    def update(self, ds_id: str, **fields) -> None:
        fields["updated_at"] = time.time()
        self.col.update_one({"_id": ds_id}, {"$set": fields})

    def set_credentials(self, ds_id: str, credentials: Dict[str, str]) -> None:
        enc = {k: encrypt(v) for k, v in credentials.items() if v is not None}
        self.col.update_one({"_id": ds_id}, {"$set": {"credentials": enc, "updated_at": time.time()}})

    def set_status(self, ds_id: str, status: str, **extra) -> None:
        extra.update({"status": status, "updated_at": time.time()})
        self.col.update_one({"_id": ds_id}, {"$set": extra})

    def delete(self, ds_id: str) -> bool:
        return self.col.delete_one({"_id": ds_id}).deleted_count > 0

    def count(self, tenant: Optional[str] = None) -> int:
        return self.col.count_documents({"tenant": tenant} if tenant else {})

    @staticmethod
    def public(doc: Dict[str, Any]) -> Dict[str, Any]:
        """去除凭证，返回可对外暴露的视图。"""
        out = dict(doc)
        out.pop("credentials", None)
        out["has_credentials"] = bool(doc.get("credentials"))
        return out
