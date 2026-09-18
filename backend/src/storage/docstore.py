"""MongoDB Docstore —— 节点真相源。

对应概念：LlamaIndex 的 MongoDocumentStore / 学习手册 03 篇。
职责：保存每个切分节点的「文本 + metadata」，是系统的 Source of Truth。
- 向量索引(Chroma)损坏时，可从这里读取全部文本重新生成 embedding 重建索引
- 所有复杂的结构化查询 / 按文档聚合 / 版本管理都在这里做

核心表：agentic_rag.nodes
字段设计：
  _id           = node_id（唯一）
  ref_doc_id    所属文档 id
  doc_name      文档名
  tenant        租户（多租户隔离用）
  doc_type      文档类型
  chunk_idx     在文档内的切分序号
  text          节点文本
  metadata      额外元数据（dict）
  text_hash     文本 hash（去重/变更检测）
  doc_version   文档版本号（增量更新用）
  created_at    写入时间
"""

import hashlib
import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


def md5(text: str) -> str:
    """计算文本指纹（去重/变更检测的基础）。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class MongoDocStore:
    """MongoDB 文档仓库。"""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.uri = uri or env["MONGO_URI"]
        self.db_name = db_name or env["MONGO_DB"]
        self.client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[self.db_name]
        self.col = self.db["nodes"]
        # 建立索引：node_id 唯一；按租户/文档聚合查询加速
        self.col.create_index("node_id", unique=True)
        self.col.create_index([("ref_doc_id", 1), ("doc_version", 1)])
        self.col.create_index("tenant")

    # ---------- 写入 ----------

    def put_node(self, node: Dict[str, Any]) -> None:
        """写入/覆盖单个节点（upsert）。"""
        node = dict(node)
        node["_id"] = node["node_id"]
        node.setdefault("created_at", time.time())
        self.col.replace_one({"_id": node["_id"]}, node, upsert=True)

    def put_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """批量写入，返回写入数量。"""
        for node in nodes:
            self.put_node(node)
        return len(nodes)

    # ---------- 读取 ----------

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        doc = self.col.find_one({"node_id": node_id})
        return doc if doc else None

    def get_nodes(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """按 node_id 列表批量取回（保持传入顺序）。"""
        found = {d["node_id"]: d for d in self.col.find({"node_id": {"$in": node_ids}})}
        return [found[i] for i in node_ids if i in found]

    def get_nodes_by_ref_doc(self, ref_doc_id: str) -> List[Dict[str, Any]]:
        return list(self.col.find({"ref_doc_id": ref_doc_id}))

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """全量节点（重建向量索引时用）。"""
        return list(self.col.find())

    def count(self) -> int:
        return self.col.count_documents({})

    # ---------- 删除 / 更新 ----------

    def delete_by_ref_doc(self, ref_doc_id: str) -> int:
        """删除某文档的全部节点（配合增量更新：旧版本先清再写）。"""
        res = self.col.delete_many({"ref_doc_id": ref_doc_id})
        return res.deleted_count

    def update_doc_version(self, ref_doc_id: str, version: int) -> None:
        self.col.update_many(
            {"ref_doc_id": ref_doc_id},
            {"$set": {"doc_version": version}},
        )


if __name__ == "__main__":
    # 自测：写入 → 读取 → 删除
    ds = MongoDocStore()
    demo = {
        "node_id": "demo-node-1",
        "ref_doc_id": "demo-doc",
        "doc_name": "demo.md",
        "tenant": "demo",
        "doc_type": "md",
        "chunk_idx": 0,
        "text": "这是一段测试文本",
        "metadata": {"title": "测试"},
        "text_hash": md5("这是一段测试文本"),
        "doc_version": 1,
    }
    ds.put_node(demo)
    print("写入后 count =", ds.count())
    print("读回 text =", ds.get_node("demo-node-1")["text"])
    ds.delete_by_ref_doc("demo-doc")
    print("删除后 count =", ds.count())
