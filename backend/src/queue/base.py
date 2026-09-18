"""队列抽象接口：Producer / Consumer。

为什么先把接口定义清楚：
  1. 上层（ingestion）只依赖抽象，不关心底下是 Kafka 还是内存队列
  2. 教学上先讲"消息队列该有什么操作"，再讲"Kafka 怎么实现"
  3. 换实现（比如以后用 RabbitMQ）零改动上层代码

关键设计：消息用 dict（JSON 可序列化），Kafka 里就是 value 的 bytes。
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Message:
    """一条消息：topic + key + value(dict) + 消费元信息。"""

    def __init__(self, topic: str, key: str, value: Dict[str, Any],
                 partition: int = 0, offset: int = -1):
        self.topic = topic
        self.key = key
        self.value = value
        self.partition = partition
        self.offset = offset

    def __repr__(self) -> str:  # 打印调试友好
        return f"<Message {self.topic}:{self.partition}:{self.offset} key={self.key}>"


class Producer(ABC):
    @abstractmethod
    def produce(self, topic: str, key: str, value: Dict[str, Any]) -> None:
        """发送一条消息。key 用于分区路由：相同 key 进同一分区（保序）。"""

    @abstractmethod
    def flush(self) -> None:
        """阻塞直到缓冲的消息全部发出（确保不丢）。"""


class Consumer(ABC):
    @abstractmethod
    def poll(self, timeout_ms: int = 1000) -> List[Message]:
        """拉一批消息。返回空列表表示暂时没有新消息。"""

    @abstractmethod
    def commit(self, messages: List[Message]) -> None:
        """确认已成功处理这批消息（提交偏移，避免重复消费）。"""

    @abstractmethod
    def close(self) -> None:
        """优雅关闭：停止拉取、释放连接。"""


def new_message_id() -> str:
    """消息唯一 id（幂等键 / 审计用）。"""
    return "msg-" + uuid.uuid4().hex[:16]
