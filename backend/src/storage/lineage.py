"""数据血缘（对应 v2 手册 07 篇）。

血缘回答一个生产问题："这条回答凭什么这么说？引用了哪份文档的哪个版本？"
记录两类边：
  - doc → node    ：切分阶段（doc 的哪些 node 是从它来的）
  - node → answer ：回答阶段（这条回答用了哪些 node）

为什么要控制写入量：
  answer 级血缘如果每条都全量存，会随问答量无限膨胀。
  策略：node → answer 只记"引用计数 + 最新引用"，不记全部历史，
  doc → node 在 ingest 时重写（文档更新后旧边自然被覆盖）。

表：agentic_rag.lineage（doc→node） + agentic_rag.answer_refs（node→answer 计数）
"""

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class LineageStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.doc_col = self.db["lineage"]
        self.ans_col = self.db["answer_refs"]

    # ---------- doc → node（ingest 时写） ----------

    def record_doc_nodes(self, ref_doc_id: str, node_ids: List[str], doc_version: int) -> None:
        """记录一篇文档切分出了哪些 node（文档更新时整条覆盖，天然防旧边残留）。"""
        self.doc_col.replace_one(
            {"_id": ref_doc_id},
            {"_id": ref_doc_id, "node_ids": node_ids, "doc_version": doc_version, "ts": time.time()},
            upsert=True,
        )

    def get_doc_nodes(self, ref_doc_id: str) -> List[str]:
        doc = self.doc_col.find_one({"_id": ref_doc_id})
        return doc["node_ids"] if doc else []

    # ---------- node → answer（回答时计数） ----------

    def record_answer_refs(self, node_ids: List[str], answer_id: str, request_id: str) -> None:
        """给被引用的 node 计数 +1，同时记最近一次引用来源。"""
        for nid in set(node_ids):
            self.ans_col.update_one(
                {"_id": nid},
                {"$inc": {"ref_count": 1},
                 "$set": {"last_answer_id": answer_id, "last_request_id": request_id, "ts": time.time()}},
                upsert=True,
            )

    def get_node_refs(self, node_id: str) -> Dict[str, Any]:
        doc = self.ans_col.find_one({"_id": node_id})
        return doc or {"ref_count": 0}

    def top_referenced(self, limit: int = 10) -> List[Dict[str, Any]]:
        """被引用最多的 node（排查"哪段文档最常被用到"，指导内容维护）。"""
        return list(self.ans_col.find().sort("ref_count", -1).limit(limit))


if __name__ == "__main__":
    ls = LineageStore()
    ls.record_doc_nodes("doc-demo", ["n1", "n2"], 1)
    print("doc 血缘:", ls.get_doc_nodes("doc-demo"))
    ls.record_answer_refs(["n1", "n2"], "ans-1", "req-1")
    print("node n1 引用:", ls.get_node_refs("n1"))
