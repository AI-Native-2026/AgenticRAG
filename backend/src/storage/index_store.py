"""MongoDB IndexStore —— 索引结构与索引元数据。

对应概念：LlamaIndex 的 MongoIndexStore / 学习手册 03 篇。
职责：记录"系统里有几个索引、每个索引覆盖哪些节点、用什么 embedding 模型建的"。
多个索引（向量索引 / BM25 索引 / 摘要索引…）共享同一批 docstore 节点，
各自只在这里保存一份轻量的 index_struct。

核心表：agentic_rag.indexes
字段设计：
  _id            = index_name（唯一）
  index_type     索引类型（vector / bm25 / summary …）
  node_ids       覆盖的节点 id 列表
  embedding_model建索引所用的 embedding 模型（模型升级后据此判断哪些要重建）
  embed_dim      向量维度
  extra          附加元数据（创建时间等）
"""

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env
from src.storage.mongo import get_client


class MongoIndexStore:
    """MongoDB 索引元数据仓库。"""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.uri = uri or env["MONGO_URI"]
        self.db_name = db_name or env["MONGO_DB"]
        self.client = get_client(self.uri)
        self.db = self.client[self.db_name]
        self.col = self.db["indexes"]
        self.col.create_index("index_name", unique=True)

    def put_index(self, index: Dict[str, Any]) -> None:
        index = dict(index)
        index["_id"] = index["index_name"]
        index.setdefault("created_at", time.time())
        self.col.replace_one({"_id": index["_id"]}, index, upsert=True)

    def get_index(self, index_name: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"index_name": index_name})

    def delete_index(self, index_name: str) -> int:
        return self.col.delete_one({"index_name": index_name}).deleted_count

    def list_indexes(self) -> List[Dict[str, Any]]:
        return list(self.col.find())


if __name__ == "__main__":
    istore = MongoIndexStore()
    demo_index = {
        "index_name": "vector_demo",
        "index_type": "vector",
        "node_ids": ["n1", "n2"],
        "embedding_model": "bge-small-zh-v1.5",
        "embed_dim": 512,
        "extra": {"note": "demo"},
    }
    istore.put_index(demo_index)
    print("读回 index_type =", istore.get_index("vector_demo")["index_type"])
    istore.delete_index("vector_demo")
    print("删除后列表 =", istore.list_indexes())
