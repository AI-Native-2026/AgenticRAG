"""文档变更生产者（对应 v2 手册 03 篇）。

把"文档来了"这件事变成一条消息发到 Kafka，而不是立即同步处理。
为什么这么做（大规模场景的核心动机）：
  1. 削峰：高峰期文档批量导入时，在线检索/Agent 服务不受影响
  2. 解耦：生产方（API/CLI）不关心消费方（embedding/写库）怎么实现
  3. 可靠：消息落 Kafka，消费失败可重试、可重放，不丢

消息结构（value）：
  {
    "request_id": 链路追踪 id（从 API 一路传进来）
    "ref_doc_id": 文档 id（ref_doc_id_of(path)）
    "doc_name"  : 文件名
    "tenant"    : 租户
    "doc_type"  : 类型
    "text"      : 文档全文
    "op"        : add | update | delete   （目前支持 add/update）
    "version"   : 版本号（由消费端 dedup 决定，这里先带 -1 由消费端裁决）
    "event_time": 事件时间
  }
"""

import time
from typing import Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env
from src.queue.base import Producer, new_message_id


class DocumentProducer:
    """把文档变更发布到队列。"""

    def __init__(self, producer: Optional[Producer] = None):
        env = get_env()
        self.env = env
        self.producer = producer or self._make_producer()
        self.topic = env["TOPIC_DOC_INGEST"]

    def _make_producer(self) -> Producer:
        from src.queue.dev_backend import get_backend

        backend = get_backend(self.env["QUEUE_BACKEND"])
        return backend["producer"]()

    def publish_docs(self, docs: List[Dict[str, str]], request_id: str = "cli") -> int:
        """把一批文档发布进队列，返回发布数量。

        key = tenant 用于 Kafka 分区路由：同一租户的文档进同一分区，
        保证同一租户内文档处理顺序（分片级有序）。
        """
        count = 0
        for doc in docs:
            self.producer.produce(
                topic=self.topic,
                key=doc["tenant"],
                value={
                    "message_id": new_message_id(),
                    "request_id": request_id,
                    "ref_doc_id": doc["ref_doc_id"],
                    "doc_name": doc["doc_name"],
                    "tenant": doc["tenant"],
                    "doc_type": doc["doc_type"],
                    "text": doc["text"],
                    "op": "add",
                    "version": -1,  # 由消费端 dedup 裁决（-1 表示未知）
                    "event_time": time.time(),
                },
            )
            count += 1
        self.producer.flush()
        return count


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.ingestion.loader import DocumentLoader

    docs = DocumentLoader().load()
    p = DocumentProducer()
    n = p.publish_docs(docs, request_id="cli-demo")
    print(f"已发布 {n} 篇文档到 topic={p.topic}（QUEUE_BACKEND={p.env['QUEUE_BACKEND']}）")
