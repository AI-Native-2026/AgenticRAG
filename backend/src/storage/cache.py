"""Redis 缓存层（对应学习手册 05 篇）。

三类缓存，各解决一个大问题：
1. embedding 缓存  : 相同文本不重复调 embedding 模型 → 省算力（GPU）与时间
2. 检索结果缓存    : 相同/相似 query 直接返回 → 省向量库与重排开销
3. 语义缓存        : 语义相近的 query 复用上一次 LLM 答案 → 省 token 成本（大规模场景省钱关键）
"""

import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def cosine_sim(a: List[float], b: List[float]) -> float:
    """余弦相似度（embedding 已归一化时可简化为点积）。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class CacheClient:
    """Redis 缓存封装。"""

    def __init__(self, url: Optional[str] = None, ttl: int = 86400):
        env = get_env()
        import redis

        self.url = url or env["REDIS_URI"]
        self.redis = redis.Redis.from_url(self.url, decode_responses=True)
        self.ttl = ttl
        self.semantic_key = "semantic_cache"  # Redis List，存 {query, answer, embedding}

    # ---------- 1) embedding 缓存 ----------

    def _emb_key(self, text: str) -> str:
        return f"emb:{md5(text)}"

    def get_embedding(self, text: str) -> Optional[List[float]]:
        raw = self.redis.get(self._emb_key(text))
        return json.loads(raw) if raw else None

    def set_embedding(self, text: str, embedding: List[float]) -> None:
        self.redis.set(self._emb_key(text), json.dumps(embedding), ex=self.ttl)

    # ---------- 2) 检索结果缓存 ----------

    def _ret_key(self, query: str, where: Optional[Dict[str, Any]], top_k: int) -> str:
        return f"ret:{md5(query)}:{json.dumps(where or {}, sort_keys=True)}:{top_k}"

    def get_retrieval(self, query: str, where: Optional[Dict[str, Any]], top_k: int) -> Optional[List[Dict[str, Any]]]:
        raw = self.redis.get(self._ret_key(query, where, top_k))
        return json.loads(raw) if raw else None

    def set_retrieval(self, query: str, where: Optional[Dict[str, Any]], top_k: int, results: List[Dict[str, Any]]) -> None:
        self.redis.set(self._ret_key(query, where, top_k), json.dumps(results), ex=min(self.ttl, 3600))

    # ---------- 3) 语义缓存 ----------

    def find_semantic(self, query_embedding: List[float], threshold: float = 0.92) -> Optional[str]:
        """在缓存中找语义相近的历史 query，返回其答案。"""
        total = self.redis.llen(self.semantic_key)
        for i in range(total):
            raw = self.redis.lindex(self.semantic_key, i)
            if not raw:
                continue
            item = json.loads(raw)
            if cosine_sim(item["embedding"], query_embedding) >= threshold:
                return item["answer"]
        return None

    def put_semantic(self, query: str, query_embedding: List[float], answer: str) -> None:
        """写入语义缓存，并限制列表长度防无限增长。"""
        item = {"query": query, "embedding": query_embedding, "answer": answer}
        self.redis.rpush(self.semantic_key, json.dumps(item))
        self.redis.ltrim(self.semantic_key, -200, -1)  # 只保留最近 200 条

    def invalidate(self, ref_doc_id: Optional[str] = None) -> None:
        """失效检索缓存。文档更新后可调用（教学点：缓存一致性）。"""
        for key in self.redis.scan_iter("ret:*"):
            self.redis.delete(key)
        if ref_doc_id:
            self.redis.delete(f"doc:{ref_doc_id}")


if __name__ == "__main__":
    cc = CacheClient()
    cc.set_embedding("测试文本", [0.1, 0.2, 0.3])
    print("embedding 缓存读回:", cc.get_embedding("测试文本"))
    cc.set_retrieval("问题", {}, 5, [{"node_id": "n1"}])
    print("检索缓存读回:", cc.get_retrieval("问题", {}, 5))
    cc.put_semantic("你叫什么", [0.1, 0.2, 0.3], "我叫测试助手")
    print("语义缓存命中:", cc.find_semantic([0.1, 0.2, 0.3]))
    cc.redis.flushdb()
