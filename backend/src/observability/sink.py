"""事件落盘 Sink。

设计：
  默认写 JSONL 文件（按天分片 events-YYYYMMDD.jsonl），读聚合脚本直接扫文件。
  可切换到 Mongo（events 集合）——教学里 JSONL 足够且更好查，生产换 Mongo 只需换 Sink 实现。

为什么按天分片：
  文件会无限增长；按天分片让"聚合最近 24h"天然退化为"只扫今天的文件"，
  也方便归档/清理。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class JsonlEventSink:
    """把事件追加写到按天分片的 JSONL 文件。线程安全（多请求并发写不串行）。"""

    def __init__(self, base_dir: Optional[str] = None):
        env = get_env()
        self.base_dir = Path(base_dir or f"{env['PROJECT_ROOT']}/logs")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._current_day: Optional[str] = None
        self._handle = None

    def _day(self) -> str:
        import time

        return time.strftime("%Y%m%d")

    def _open_today(self):
        day = self._day()
        if self._handle is None or self._current_day != day:
            if self._handle:
                self._handle.close()
            self._current_day = day
            self._handle = open(self.base_dir / f"events-{day}.jsonl", "a", encoding="utf-8")
        return self._handle

    def record(self, evt: Dict[str, Any]) -> None:
        """写一条事件。加锁防止多线程同时写同一文件。"""
        from src.observability.events import to_json

        with self._lock:
            handle = self._open_today()
            handle.write(to_json(evt) + "\n")
            handle.flush()

    def read_all(self, days: int = 1) -> List[Dict[str, Any]]:
        """读最近 N 天的事件（聚合脚本用）。"""
        from datetime import datetime, timedelta

        events: List[Dict[str, Any]] = []
        today = datetime.now()
        for i in range(days):
            day = (today - timedelta(days=i)).strftime("%Y%m%d")
            path = self.base_dir / f"events-{day}.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        events.append(json.loads(line))
        return events

    def close(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None


# 全局单例：全进程共用同一个 sink，避免重复开文件句柄
_singleton: Optional[JsonlEventSink] = None


def get_sink() -> JsonlEventSink:
    global _singleton
    if _singleton is None:
        _singleton = JsonlEventSink()
    return _singleton


if __name__ == "__main__":
    sink = get_sink()
    sink.record({"ts": 0, "request_id": "req-demo", "event_type": "generate", "tenant": "tech", "tokens": 100})
    print("已写入，文件列表:", [p.name for p in sink.base_dir.glob("events-*.jsonl")])
