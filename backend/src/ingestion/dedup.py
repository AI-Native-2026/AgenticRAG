"""去重 + 变更检测 + 版本管理（对应学习手册 03 篇增量更新部分）。

大规模场景下，文档每天在变，直接全量重建不现实。本模块解决：
1. 去重   ：同一文件重复上传/重跑，hash 相同直接跳过，省 embedding 成本
2. 变更检测：hash 不同 → 判定为"更新"，走 旧版清理 → 新版写入
3. 版本管理：每篇文档维护递增的 version，配合 docstore/chroma 里的 doc_version 字段

表：agentic_rag.documents
  _id         = ref_doc_id
  text_hash   全文 hash（变更检测）
  version     当前版本号
  chunk_count 节点数
  updated_at  更新时间
"""

import time
from typing import Any, Dict, Optional, Tuple

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class DocDedup:
    """文档去重/版本记录（基于 MongoDB）。"""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["documents"]

    def get_record(self, ref_doc_id: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": ref_doc_id})

    def decide(self, ref_doc_id: str, text_hash: str) -> Tuple[str, int]:
        """决策一个文档该怎样处理。

        返回 (action, next_version)
        - action = "skip"   : 内容没变，跳过
        - action = "insert" : 新文档，直接写入
        - action = "update" : 内容变了，先清旧版再写入
        """
        record = self.get_record(ref_doc_id)
        if record is None:
            return "insert", 1
        if record["text_hash"] == text_hash:
            return "skip", record["version"]
        return "update", record["version"] + 1

    def save_record(self, ref_doc_id: str, text_hash: str, version: int, chunk_count: int) -> None:
        self.col.replace_one(
            {"_id": ref_doc_id},
            {
                "_id": ref_doc_id,
                "text_hash": text_hash,
                "version": version,
                "chunk_count": chunk_count,
                "updated_at": time.time(),
            },
            upsert=True,
        )


if __name__ == "__main__":
    dd = DocDedup()
    print("skip 场景:", dd.decide("doc-nope", "hash-x"))
    print("insert:", dd.decide("doc-new", "hash-1"))
    dd.save_record("doc-new", "hash-1", 1, 3)
    print("再次(相同):", dd.decide("doc-new", "hash-1"))
    print("再次(变了):", dd.decide("doc-new", "hash-2"))
