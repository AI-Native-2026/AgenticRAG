"""启动队列消费者（v2）。

用法：python scripts/run_consumer.py
      nohup python scripts/run_consumer.py > /root/autodl-tmp/agentic_rag_v2/logs/consumer.log 2>&1 &

消费者会一直拉取 doc_ingest 队列，处理文档建索引。
Ctrl-C / kill 触发优雅停机（处理完当前批次再退出）。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_env  # noqa: E402
from src.ingestion.consumer import DocumentConsumer  # noqa: E402


def main():
    env = get_env()
    print(f"QUEUE_BACKEND={env['QUEUE_BACKEND']}  KAFKA={env['KAFKA_BOOTSTRAP']}")
    DocumentConsumer().run()


if __name__ == "__main__":
    main()
