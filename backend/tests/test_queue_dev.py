"""dev 队列后端测试（无 Kafka 也能验证队列语义）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.queue.dev_backend import DevConsumer, DevProducer, new_dev_store  # noqa: E402


def test_produce_consume_roundtrip():
    store = new_dev_store()
    producer = DevProducer(store)
    consumer = DevConsumer(store, topics=["t1"], group_id="g")

    producer.produce("t1", key="k", value={"doc": 1})
    producer.flush()

    messages = consumer.poll(timeout_ms=100)
    assert len(messages) == 1
    assert messages[0].value == {"doc": 1}
    assert messages[0].key == "k"


def test_fifo_order():
    """同一 topic 内先进先出。"""
    store = new_dev_store()
    producer = DevProducer(store)
    consumer = DevConsumer(store, topics=["t"], group_id="g")

    for i in range(5):
        producer.produce("t", key="k", value={"seq": i})
    got = [m.value["seq"] for m in consumer.poll(timeout_ms=100)]
    assert got == [0, 1, 2, 3, 4]  # 顺序保持


def test_empty_poll_returns_empty():
    store = new_dev_store()
    consumer = DevConsumer(store, topics=["nothing"], group_id="g")
    assert consumer.poll(timeout_ms=50) == []
