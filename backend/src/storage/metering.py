"""用量计量（对应 v2 手册 07 篇）。

计量是成本工程的底座：没有数字，就回答不了"钱花哪了、谁花的"。
计量的两种实现：
  - Redis 计数器：实时、易自增，适合 QPS / 短期突发统计
  - Mongo 聚合  ：持久、适合跨天统计与报表

本模块：按租户累计 token（prompt/completion）与请求数，写 Mongo。
LLM 网关每次响应后调用 record_generate()，把真实 usage 落库。
"""

import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class Metering:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["metering"]
        self.col.create_index([("tenant", 1), ("day", 1)])

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d")

    def record_generate(self, tenant: str, prompt_tokens: int, completion_tokens: int) -> None:
        """每次 LLM 生成后调用：按 (tenant, day) 累加 token。"""
        self.col.update_one(
            {"tenant": tenant, "day": self._today()},
            {"$inc": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "calls": 1}},
            upsert=True,
        )

    def daily_usage(self, tenant: Optional[str] = None, days: int = 7) -> Dict[str, Any]:
        """最近 N 天用量（admin 报表用）。"""
        from datetime import datetime, timedelta

        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        filt: Dict[str, Any] = {"day": {"$gte": start}}
        if tenant:
            filt["tenant"] = tenant
        docs = list(self.col.find(filt))
        return {
            "total_prompt": sum(d.get("prompt_tokens", 0) for d in docs),
            "total_completion": sum(d.get("completion_tokens", 0) for d in docs),
            "total_calls": sum(d.get("calls", 0) for d in docs),
            "by_tenant": {
                t: {"prompt": sum(d.get("prompt_tokens", 0) for d in docs if d["tenant"] == t),
                    "completion": sum(d.get("completion_tokens", 0) for d in docs if d["tenant"] == t)}
                for t in {d["tenant"] for d in docs}
            },
        }


if __name__ == "__main__":
    m = Metering()
    m.record_generate("tech", prompt_tokens=100, completion_tokens=50)
    print("近7天用量:", m.daily_usage())
