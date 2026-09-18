"""开发后端：纯内存队列。

什么时候用它：
  - 本地没有 Kafka broker 时开发/联调
  - 单元测试（tests/ 里的队列测试就跑在它上面，快且无外部依赖）

为什么教学上也要留它：
  Kafka 的「队列」本质是一套分布式协议，但核心语义（先进先出、
  按 key 分区保序、偏移提交、消费者组）在内存队列里 1:1 复刻，
  学生先在简单的实现里理解概念，再切到 Kafka 验证行为一致。
"""

import queue
import threading
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env
from src.queue.base import Consumer, Message, Producer
from src.queue.kafka_backend import KafkaConsumerImpl, KafkaProducerImpl


class DevProducer(Producer):
    def __init__(self, store: Dict[str, queue.Queue]):
        self.store = store  # topic -> Queue
        self._lock = threading.Lock()

    def produce(self, topic: str, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            q = self.store.setdefault(topic, queue.Queue())
            q.put({"key": key, "value": value, "seq": q.qsize()})

    def flush(self) -> None:
        pass  # 内存队列天然立即可见，无需 flush


class DevConsumer(Consumer):
    def __init__(self, store: Dict[str, queue.Queue], topics: List[str], group_id: str):
        self.store = store
        self.topics = topics
        self._closed = False

    def poll(self, timeout_ms: int = 1000) -> List[Message]:
        """拉取：持续取到队列空或超时（贴近 Kafka 的批量拉取语义）。"""
        msgs: List[Message] = []
        import time

        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            drained = False
            for topic in self.topics:
                q = self.store.get(topic)
                if not q:
                    continue
                try:
                    item = q.get(timeout=0.02)
                    msgs.append(Message(
                        topic=topic, key=item["key"], value=item["value"],
                        partition=0, offset=item["seq"],
                    ))
                    drained = True
                except queue.Empty:
                    continue
            if not drained:
                break  # 所有队列都空了，提前返回
        return msgs

    def commit(self, messages: List[Message]) -> None:
        # 内存队列里"取走即确认"，commit 是空操作（语义上等价于已处理）
        pass

    def close(self) -> None:
        self._closed = True


def new_dev_store() -> Dict[str, queue.Queue]:
    return {}


def get_backend(backend: Optional[str] = None):
    """工厂：根据环境变量 QUEUE_BACKEND（默认 kafka）返回生产/消费实现。

    用法：
      producer = get_backend("kafka")["producer"]
      consumer = get_backend("kafka")["consumer"](topics, group)
    """
    env = get_env()
    backend = backend or env.get("QUEUE_BACKEND", "kafka")
    if backend == "kafka":
        return {
            "producer": KafkaProducerImpl,
            "consumer": KafkaConsumerImpl,
        }
    store = new_dev_store()
    return {
        "producer": lambda: DevProducer(store),
        "consumer": lambda topics, group: DevConsumer(store, topics, group),
    }
