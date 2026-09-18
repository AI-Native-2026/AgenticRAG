"""Kafka 后端（kafka-python 实现）。

为什么用 kafka-python 而不是 confluent-kafka：
  - confluent-kafka 底层是 C 库（librdkafka），需要编译/二进制，资源受限环境易出问题
  - kafka-python 是纯 Python，pip 即装即用，功能满足教学场景
  生产大规模、追求性能时再换 confluent-kafka（接口也基本兼容）。

要点：
  - enable_auto_commit=False：关闭自动提交偏移。
    原因：如果"边拉边自动提交"但处理还没完成，进程崩了就会丢消息；
    我们手动 commit，保证「处理成功才提交」的 at-least-once 语义。
  - auto_offset_reset="earliest"：新消费者组从最早消息开始，避免漏数据。
"""

import json
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from kafka import KafkaConsumer, KafkaProducer

from src.config import get_env
from src.queue.base import Consumer, Message, Producer


class KafkaBackendMixin:
    """共享 Kafka 连接配置。"""

    def _bootstrap(self) -> str:
        env = get_env()
        return env.get("KAFKA_BOOTSTRAP", "localhost:9092")


class KafkaProducerImpl(KafkaBackendMixin, Producer):
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=self._bootstrap(),
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            # acks=1：leader 落盘即确认，吞吐与安全的折中
            acks=1,
        )

    def produce(self, topic: str, key: str, value: Dict[str, Any]) -> None:
        self.producer.send(topic, key=key.encode("utf-8"), value=value)

    def flush(self) -> None:
        self.producer.flush()


class KafkaConsumerImpl(KafkaBackendMixin, Consumer):
    def __init__(self, topics: List[str], group_id: str):
        # 反序列化必须健壮：topic 里可能有历史脏数据（非 JSON），
        # 遇到解析失败返回 None，poll 时跳过，不能让一条坏消息搞崩消费者
        def safe_json(b: bytes):
            try:
                return json.loads(b.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=self._bootstrap(),
            group_id=group_id,
            enable_auto_commit=False,       # 手动提交（见模块 docstring）
            auto_offset_reset="earliest",
            value_deserializer=safe_json,
            key_deserializer=lambda b: b.decode("utf-8") if b else "",
            # 拉取控制：5s 拉不到新消息就返回，保证 poll 不长期阻塞（配合优雅停机）
            consumer_timeout_ms=5000,
        )

    def poll(self, timeout_ms: int = 1000) -> List[Message]:
        messages: List[Message] = []
        for raw in self.consumer.poll(timeout_ms=timeout_ms, max_records=100).values():
            for rec in raw:
                if rec.value is None:
                    continue  # 脏数据跳过，不处理也不提交（由重放/人工清理）
                messages.append(Message(
                    topic=rec.topic,
                    key=rec.key or "",
                    value=rec.value,
                    partition=rec.partition,
                    offset=rec.offset,
                ))
        return messages

    def commit(self, messages: List[Message]) -> None:
        # 按 (topic, partition) 提交到已处理的最大 offset+1
        from kafka.structs import OffsetAndMetadata, TopicPartition

        offsets = {}
        for m in messages:
            tp = TopicPartition(m.topic, m.partition)
            offsets[tp] = OffsetAndMetadata(m.offset + 1, "")
        self.consumer.commit(offsets=offsets)

    def close(self) -> None:
        self.consumer.close()
