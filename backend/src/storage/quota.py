"""租户配额（对应 v2 手册 05 篇）。

配额 = 给租户划定的资源上限。两类配额、两种实现：
  1. QPS 配额（瞬时）    → Redis/内存令牌桶（实时），由网关 rate_limit 执行
  2. 预算配额（累计）    → 日 token 上限、存储量上限，靠 metering/docstore 统计

本模块负责"预算配额"：
  - 给租户建档（配额表）
  - 请求前检查"今天 token 是否超预算"、"存储是否超限"
  - 超限返回配额拒绝（并计一次 quota_denied 事件，供告警）

表：agentic_rag.tenants
  {_id: tenant, quota_tokens_per_day, quota_storage_nodes, created_at, admin_emails}
"""

import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


class QuotaManager:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["tenants"]

    # ---------- 租户管理 ----------

    def create_tenant(self, tenant: str, quota_tokens_per_day: int = 100000,
                      quota_storage_nodes: int = 10000) -> None:
        self.col.update_one(
            {"_id": tenant},
            {"$set": {"quota_tokens_per_day": quota_tokens_per_day,
                      "quota_storage_nodes": quota_storage_nodes,
                      "created_at": time.time()}},
            upsert=True,
        )

    def get_tenant(self, tenant: str) -> Dict[str, Any]:
        doc = self.col.find_one({"_id": tenant})
        if doc is None:
            # 未建档的租户给默认宽松配额（避免误伤新租户）
            return {"quota_tokens_per_day": 100000, "quota_storage_nodes": 10000}
        return doc

    # ---------- 配额检查 ----------

    def check_token_quota(self, tenant: str) -> bool:
        """今天 token 消耗是否超预算。超则返回 False（拒绝）。"""
        from src.storage.metering import Metering

        q = self.get_tenant(tenant)
        usage = Metering().daily_usage(tenant=tenant, days=1)
        used = usage["total_prompt"] + usage["total_completion"]
        return used < q["quota_tokens_per_day"]

    def check_storage_quota(self, tenant: str) -> bool:
        """该租户当前存储的节点数是否超限。"""
        from src.storage.docstore import MongoDocStore

        q = self.get_tenant(tenant)
        ds = MongoDocStore()
        count = ds.col.count_documents({"tenant": tenant})
        return count < q["quota_storage_nodes"]

    def list_tenants(self) -> list:
        return list(self.col.find())


if __name__ == "__main__":
    qm = QuotaManager()
    qm.create_tenant("demo", quota_tokens_per_day=5000, quota_storage_nodes=100)
    print("租户列表:", qm.list_tenants())
    print("token 配额充足?", qm.check_token_quota("demo"))
