"""知识库（Knowledge Base）。

知识库 = 一组数据源的逻辑分组，是 Agent 检索的目标范围。
表：agentic_rag.knowledge_bases
  {_id: kb_id, name, slug, description, tenant, datasource_ids: [],
   status, created_at, updated_at}
"""

import re
import time
import uuid
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env
from src.storage.mongo import get_client


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", name.strip().lower()).strip("-")
    return s or "kb"


class KnowledgeBaseStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = get_client(uri or env["MONGO_URI"])
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["knowledge_bases"]
        self.col.create_index("tenant")

    def create(self, name: str, tenant: str, description: str = "",
               slug: Optional[str] = None, datasource_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        kb_id = "kb-" + uuid.uuid4().hex[:12]
        doc = {
            "_id": kb_id,
            "kb_id": kb_id,
            "name": name,
            "slug": slug or _slugify(name),
            "description": description,
            "tenant": tenant,
            "datasource_ids": datasource_ids or [],
            "status": "ready",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.col.insert_one(doc)
        return doc

    def get(self, kb_id: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": kb_id})

    def list(self, tenant: Optional[str] = None) -> List[Dict[str, Any]]:
        q = {"tenant": tenant} if tenant else {}
        return list(self.col.find(q).sort("created_at", -1))

    def update(self, kb_id: str, **fields) -> None:
        fields["updated_at"] = time.time()
        self.col.update_one({"_id": kb_id}, {"$set": fields})

    def add_datasource(self, kb_id: str, datasource_id: str) -> None:
        self.col.update_one({"_id": kb_id}, {"$addToSet": {"datasource_ids": datasource_id},
                                             "$set": {"updated_at": time.time()}})

    def remove_datasource(self, kb_id: str, datasource_id: str) -> None:
        self.col.update_one({"_id": kb_id}, {"$pull": {"datasource_ids": datasource_id},
                                             "$set": {"updated_at": time.time()}})

    def delete(self, kb_id: str) -> bool:
        return self.col.delete_one({"_id": kb_id}).deleted_count > 0

    def count(self, tenant: Optional[str] = None) -> int:
        return self.col.count_documents({"tenant": tenant} if tenant else {})
