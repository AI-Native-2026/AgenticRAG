"""索引流水线（对应学习手册 03 篇）。

把整条离线链路串起来：
  加载文档 → 切分 → 去重/版本决策 → 批量 embedding(带缓存, GPU) → 写 docstore + chroma
  → 更新版本/索引元数据

大规模语义在这里体现：
- 批量 embedding：一次喂多段文本给 GPU，远快于逐条调用
- embedding 缓存：相同文本不重算
- 增量更新：只处理变了的文档，旧向量按 ref_doc_id 清理
- 幂等：同一批数据重复跑不会重复写入
"""

import logging
import time
from typing import Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from llama_index.core.base.embeddings.base import BaseEmbedding

from src.config import get_env
from src.ingestion.chunker import Chunker
from src.ingestion.dedup import DocDedup
from src.ingestion.loader import DocumentLoader
from src.storage.cache import CacheClient
from src.storage.docstore import MongoDocStore, md5
from src.storage.index_store import MongoIndexStore
from src.storage.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """文档 → 向量的完整离线流水线。"""

    def __init__(
        self,
        embed_model: BaseEmbedding,
        docstore: MongoDocStore,
        vector_store: ChromaVectorStore,
        index_store: MongoIndexStore,
        cache: Optional[CacheClient] = None,
    ):
        self.embed_model = embed_model
        self.docstore = docstore
        self.vector_store = vector_store
        self.index_store = index_store
        self.cache = cache
        self.dedup = DocDedup()
        self.loader = DocumentLoader()
        self.chunker = Chunker()
        self.env = get_env()

    def run(self) -> Dict[str, int]:
        """执行一次全量/增量同步，返回统计信息。"""
        docs = self.loader.load()
        stats = {"total": len(docs), "insert": 0, "update": 0, "skip": 0, "chunks": 0}
        logger.info("加载到 %d 篇文档", len(docs))

        for doc in docs:
            text_hash = md5(doc["text"])
            action, version = self.dedup.decide(doc["ref_doc_id"], text_hash)

            if action == "skip":
                stats["skip"] += 1
                continue

            nodes = self.chunker.recursive_split(doc, doc_version=version)
            if not nodes:
                continue

            if action == "update":
                # 旧版本数据先清掉（docstore + 向量），保证一致性
                self.docstore.delete_by_ref_doc(doc["ref_doc_id"])
                self.vector_store.delete_by_ref_doc(doc["ref_doc_id"])
                if self.cache:
                    self.cache.invalidate(doc["ref_doc_id"])

            # 1) 写 docstore（真相源）
            self.docstore.put_nodes(nodes)
            # 2) 批量 embedding（带缓存）
            embeddings = self._embed_texts([n["text"] for n in nodes])
            # 3) 写向量库
            self.vector_store.add_nodes(nodes, embeddings)
            # 4) 记录版本
            self.dedup.save_record(doc["ref_doc_id"], text_hash, version, len(nodes))

            stats[action] += 1
            stats["chunks"] += len(nodes)
            logger.info("[%s] %s/%s v%d → %d chunks", action, doc["tenant"], doc["doc_name"], version, len(nodes))

        # 写一份索引元数据（embbeding 模型版本，便于以后判断要不要重建）
        self.index_store.put_index({
            "index_name": "vector_main",
            "index_type": "vector",
            "node_ids": [],
            "embedding_model": self.env["BGE_EMBED_PATH"],
            "embed_dim": int(self.env["EMBED_DIM"]),
            "extra": {"vector_count": self.vector_store.count(), "run_at": time.time()},
        })
        return stats

    def _embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量 embedding，命中缓存则跳过，未命中才调 GPU 模型。"""
        results: List[List[float]] = []
        pending_texts: List[str] = []
        pending_idx: List[int] = []

        for i, text in enumerate(texts):
            cached = self.cache.get_embedding(text) if self.cache else None
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                pending_texts.append(text)
                pending_idx.append(i)

        if pending_texts:
            for start in range(0, len(pending_texts), batch_size):
                batch = pending_texts[start : start + batch_size]
                vecs = self.embed_model.get_text_embedding_batch(batch)
                for local_i, vec in enumerate(vecs):
                    gi = pending_idx[start + local_i]
                    results[gi] = vec
                    if self.cache:
                        self.cache.set_embedding(pending_texts[start + local_i], vec)
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.llm.gateway import build_embed_model
    from src.storage.cache import CacheClient

    pipe = IngestionPipeline(
        embed_model=build_embed_model(),
        docstore=MongoDocStore(),
        vector_store=ChromaVectorStore(),
        index_store=MongoIndexStore(),
        cache=CacheClient(),
    )
    print("执行结果:", pipe.run())
    print("docstore 节点数:", pipe.docstore.count(), "| 向量数:", pipe.vector_store.count())
