"""文档变更消费者（对应 v2 手册 03 篇）。

职责：从队列拉取文档消息 → 切分 → embedding → 写 docstore + 向量库 → 提交偏移。
三个生产级要点（也是本模块的教学重点）：

1. 幂等消费（at-least-once 的兜底）
   Kafka 只保证"处理成功才提交"，但可能重复投递。我们用 dedup 的
   版本号做裁判：消息带的 version 如果 <= 已处理的版本，直接丢弃。
   这样即使同一条消息被消费两次，也不会写两遍。

2. 重试 + 死信（DLQ）
   单条消息处理失败（网络/模型抖动）先重试 N 次；仍失败进 DLQ topic，
   等人工/后续脚本处理。绝不让一条坏消息卡死整个消费者。

3. 优雅停机
   收到 SIGTERM/SIGINT 后：停止拉取 → 处理完手上这批 → 提交 → 退出。
   否则进程被 kill 的瞬间会重复消费最后一批消息。
"""

import signal
import time
from typing import Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env
from src.queue.base import Consumer, Message


class DocumentConsumer:
    def __init__(self, consumer: Optional[Consumer] = None, embed_model=None,
                 docstore=None, vector_store=None, dedup=None, cache=None,
                 index_store=None, chunker=None):
        env = get_env()
        self.env = env
        self.consumer = consumer or self._make_consumer()
        self.dlq = self._make_producer_for_dlq()
        self.dlq_topic = env["TOPIC_DOC_DLQ"]
        self.max_retry = int(env["MAX_RETRY_DOC"])

        # 延迟导入，避免模块初始化时就拉起 GPU/模型
        if embed_model is None:
            from src.llm.multimodal import get_embedder
            self.embedder = get_embedder()
        else:
            self.embedder = None
        if docstore is None:
            from src.storage.docstore import MongoDocStore
            docstore = MongoDocStore()
        if vector_store is None:
            from src.storage.vector_store import ChromaVectorStore
            vector_store = ChromaVectorStore()
        if dedup is None:
            from src.ingestion.dedup import DocDedup
            dedup = DocDedup()
        if chunker is None:
            from src.ingestion.chunker import Chunker
            chunker = Chunker()
        if cache is None:
            from src.storage.cache import CacheClient
            cache = CacheClient()
        if index_store is None:
            from src.storage.index_store import MongoIndexStore
            index_store = MongoIndexStore()

        self.embed_model = embed_model
        self.docstore = docstore        self.vector_store = vector_store
        self.dedup = dedup
        self.chunker = chunker
        self.cache = cache
        self.index_store = index_store
        self._stop = False

    # ---------- 组装 ----------

    def _make_consumer(self) -> Consumer:
        from src.queue.dev_backend import get_backend

        backend = get_backend(self.env["QUEUE_BACKEND"])
        return backend["consumer"]([self.env["TOPIC_DOC_INGEST"]],
                                   group_id=self.env.get("CONSUMER_GROUP", "ingest-group"))

    def _make_producer_for_dlq(self):
        from src.queue.dev_backend import get_backend

        backend = get_backend(self.env["QUEUE_BACKEND"])
        return backend["producer"]()

    # ---------- 消费循环 ----------

    def run(self) -> None:
        """主循环：拉取 → 处理 → 提交。注册信号处理以支持优雅停机。"""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        print(f"[consumer] 启动，topic={self.env['TOPIC_DOC_INGEST']} group={self.env.get('CONSUMER_GROUP', 'ingest-group')}")

        while not self._stop:
            messages = self.consumer.poll(timeout_ms=1000)
            for msg in messages:
                ok = self._process_with_retry(msg)
                if ok:
                    self.consumer.commit([msg])
                else:
                    # 已重试耗尽 → 进死信，提交偏移避免毒消息卡死分区
                    self._to_dlq(msg, "retry exhausted")
                    self.consumer.commit([msg])
        self.consumer.close()
        print("[consumer] 已优雅退出")

    def _process_with_retry(self, msg: Message) -> bool:
        """单条消息重试 MAX_RETRY_DOC 次；成功 True，耗尽 False。"""
        for attempt in range(1, self.max_retry + 1):
            try:
                self._process(msg)
                return True
            except Exception as e:  # noqa: BLE001
                print(f"[consumer] 处理失败 attempt={attempt}/{self.max_retry} msg={msg.key}: {e}")
                time.sleep(min(2 ** attempt * 0.2, 3.0))
        return False

    def _to_dlq(self, msg: Message, reason: str) -> None:
        """把失败消息投递到死信 topic。"""
        try:
            self.dlq.produce(
                topic=self.dlq_topic,
                key=msg.key,
                value={**(msg.value or {}), "error": reason, "failed_at": time.time()},
            )
            self.dlq.flush()
            print(f"[consumer] 已投递死信 topic={self.dlq_topic} key={msg.key}")
        except Exception as e:  # noqa: BLE001
            print(f"[consumer] 死信投递失败: {e}")

    def _handle_signal(self, signum, frame):
        print(f"[consumer] 收到信号 {signum}，开始优雅停机…")
        self._stop = True

    # ---------- 单条处理 ----------

    def _process(self, msg: Message) -> None:
        value = msg.value
        ref_doc_id = value["ref_doc_id"]
        text = value["text"]

        # 1) 幂等裁判：版本号对比。消息版本 < 已处理版本 → 丢弃
        action, version = self.dedup.decide(ref_doc_id, self._text_hash(text))
        if value.get("version", -1) >= 0 and value["version"] < version:
            return  # 过期消息，直接丢弃（不 commit 也无妨，下次同样丢弃）

        if action == "skip":
            return  # 内容没变，无需处理

        nodes = self.chunker.recursive_split(value, doc_version=version)
        if not nodes:
            return

        # 2) 更新：先清旧版（docstore + 向量 + 缓存），保证一致性
        if action == "update":
            self.docstore.delete_by_ref_doc(ref_doc_id)
            self.vector_store.delete_by_ref_doc(ref_doc_id)
            self.cache.invalidate(ref_doc_id)

        # 3) 写真相源 → 批量 embedding → 写向量库
        self.docstore.put_nodes(nodes)
        embeddings = self._embed_nodes(nodes)
        self.vector_store.add_nodes(nodes, embeddings)
        self.dedup.save_record(ref_doc_id, self._text_hash(text), version, len(nodes))

        # 4) 血缘/观测（v2）
        try:
            from src.observability.events import make_event
            from src.observability.sink import get_sink

            get_sink().record(make_event(
                "ingest_doc", request_id=value.get("request_id", "consumer"),
                tenant=value.get("tenant"), ref_doc_id=ref_doc_id, op=action,
            ))
        except Exception:  # noqa: BLE001 —— 观测失败不影响主流程
            pass

    def _text_hash(self, text: str) -> str:
        import hashlib

        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _embed_nodes(self, nodes: List[Dict]) -> List[List[float]]:
        """按节点类型 embedding（图片走多模态）+ 缓存。"""
        if self.embedder is None:
            from src.llm.multimodal import get_embedder
            self.embedder = get_embedder()
        results: List = [None] * len(nodes)
        pending, idx = [], []
        for i, n in enumerate(nodes):
            key = self._cache_key(n)
            cached = self.cache.get_embedding(key) if self.cache else None
            if cached is not None:
                results[i] = cached
            else:
                pending.append(n)
                idx.append(i)
        if pending:
            items = [{
                "text": n.get("text", ""),
                "modality": (n.get("metadata") or {}).get("modality"),
                "media_path": (n.get("metadata") or {}).get("media_path"),
            } for n in pending]
            vecs = self.embedder.embed_items(items)
            for j, v in enumerate(vecs):
                gi = idx[j]
                results[gi] = v
                if self.cache:
                    self.cache.set_embedding(self._cache_key(pending[j]), v)
        return results

    def _cache_key(self, node: Dict) -> str:
        meta = node.get("metadata") or {}
        if meta.get("modality") == "image" and meta.get("media_path"):
            from src.llm.multimodal import image_cache_key
            return image_cache_key(meta["media_path"])
        return node.get("text") or ""


if __name__ == "__main__":
    c = DocumentConsumer()
    c.run()
