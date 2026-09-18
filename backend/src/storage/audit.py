"""审计日志（对应 v2 手册 06 篇）。

记录"谁、什么时候、调了什么工具/接口、参数是什么、结果如何"。
审计和观测事件的区别：
  - 观测事件(observability) 是给"性能/成本"看的，可丢、可精简
  - 审计日志是给"合规/追责"看的，**不可篡改、必须完整、要能按用户查询**
所以审计单独落 Mongo（带索引），并保留不可变语义（只 append）。

表：agentic_rag.audit
"""

import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class AuditLog:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["audit"]
        # 审计查询最常用的三个维度：时间 / 用户(request_id/role) / 工具
        self.col.create_index([("ts", -1)])
        self.col.create_index([("request_id", 1)])
        self.col.create_index([("tool", 1)])

    def record(self, tool: str, request_id: str, role: str, args: Dict[str, Any],
               allowed: bool, ok: bool = True, duration_ms: float = 0.0) -> None:
        """写一条审计记录（只 append，不改不删）。"""
        self.col.insert_one({
            "ts": time.time(),
            "request_id": request_id,
            "role": role,
            "tool": tool,
            "args": args,
            "allowed": allowed,
            "ok": ok,
            "duration_ms": duration_ms,
        })

    def query(self, request_id: Optional[str] = None, tool: Optional[str] = None, limit: int = 50):
        """按条件查审计（合规查询入口）。"""
        filt: Dict[str, Any] = {}
        if request_id:
            filt["request_id"] = request_id
        if tool:
            filt["tool"] = tool
        return list(self.col.find(filt).sort("ts", -1).limit(limit))


if __name__ == "__main__":
    a = AuditLog()
    a.record(tool="kb_search", request_id="req-1", role="member",
             args={"query": "电池"}, allowed=True, ok=True)
    print("审计写入成功，查询结果条数:", len(a.query(request_id="req-1")))
