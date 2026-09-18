"""入库任务（Ingest Job）。

表：agentic_rag.ingest_jobs
  {_id: job_id, job_id, datasource_id, tenant, mode, status,
   progress, total, processed, chunks, skipped, deduped, failed,
   error, started_at, finished_at, request_id, stats}
"""

import time
import uuid
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env

VALID_STATUS = ("pending", "running", "success", "failed", "cancelled")


class JobStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["ingest_jobs"]
        self.col.create_index("tenant")
        self.col.create_index("datasource_id")
        self.col.create_index("status")

    def create(self, datasource_id: str, tenant: str, mode: str = "full",
               total: int = 0, request_id: str = "") -> Dict[str, Any]:
        job_id = "job-" + uuid.uuid4().hex[:12]
        doc = {
            "_id": job_id,
            "job_id": job_id,
            "datasource_id": datasource_id,
            "tenant": tenant,
            "mode": mode,
            "status": "pending",
            "progress": 0,
            "total": total,
            "processed": 0,
            "chunks": 0,
            "skipped": 0,
            "deduped": 0,
            "failed": 0,
            "error": None,
            "started_at": None,
            "finished_at": None,
            "request_id": request_id,
            "stats": {},
            "created_at": time.time(),
        }
        self.col.insert_one(doc)
        return doc

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": job_id})

    def list(self, tenant: Optional[str] = None, datasource_id: Optional[str] = None,
             status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if tenant:
            q["tenant"] = tenant
        if datasource_id:
            q["datasource_id"] = datasource_id
        if status:
            q["status"] = status
        return list(self.col.find(q).sort("created_at", -1).limit(limit))

    def start(self, job_id: str, total: int = 0) -> None:
        self.col.update_one({"_id": job_id}, {"$set": {
            "status": "running", "started_at": time.time(), "total": total,
        }})

    def progress(self, job_id: str, processed: int, total: Optional[int] = None, **counters) -> None:
        fields: Dict[str, Any] = {"processed": processed}
        if total is not None:
            fields["total"] = total
            fields["progress"] = int(100 * processed / total) if total else 0
        for k, v in counters.items():
            fields[k] = v
        self.col.update_one({"_id": job_id}, {"$set": fields})

    def finish(self, job_id: str, status: str = "success", error: Optional[str] = None,
               **stats) -> None:
        self.col.update_one({"_id": job_id}, {"$set": {
            "status": status,
            "error": error,
            "finished_at": time.time(),
            "progress": 100 if status == "success" else None,
            "stats": stats,
        }})

    def count_by_status(self, tenant: Optional[str] = None) -> Dict[str, int]:
        q = {"tenant": tenant} if tenant else {}
        out: Dict[str, int] = {}
        for s in VALID_STATUS:
            out[s] = self.col.count_documents({**q, "status": s})
        return out
