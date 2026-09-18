"""增量同步水位线。

表：agentic_rag.db_sync_state
  {_id: "<ds_id>:<resource>", datasource_id, tenant, resource,
   watermark, last_sync_at, rows_synced, status, error}
"""

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env
from src.storage.mongo import get_client


class SyncStateStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = get_client(uri or env["MONGO_URI"])
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["db_sync_state"]
        self.col.create_index("datasource_id")

    def get(self, datasource_id: str, resource: str) -> Dict[str, Any]:
        doc = self.col.find_one({"_id": f"{datasource_id}:{resource}"})
        return doc or {"datasource_id": datasource_id, "resource": resource, "watermark": None}

    def get_watermark(self, datasource_id: str, resource: str) -> Any:
        return self.get(datasource_id, resource).get("watermark")

    def set(self, datasource_id: str, resource: str, tenant: str, watermark: Any,
            rows_synced: int = 0, status: str = "ok", error: Optional[str] = None) -> None:
        self.col.update_one(
            {"_id": f"{datasource_id}:{resource}"},
            {"$set": {
                "datasource_id": datasource_id,
                "tenant": tenant,
                "resource": resource,
                "watermark": watermark,
                "rows_synced": rows_synced,
                "status": status,
                "error": error,
                "last_sync_at": time.time(),
            }},
            upsert=True,
        )

    def list(self, datasource_id: str) -> List[Dict[str, Any]]:
        return list(self.col.find({"datasource_id": datasource_id}))
