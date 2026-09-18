"""列出租户与配额（v2 admin CLI）。

用法：python scripts/admin/list_tenants.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.storage.quota import QuotaManager  # noqa: E402


def main():
    qm = QuotaManager()
    tenants = qm.list_tenants()
    if not tenants:
        print("暂无租户（用 create_tenant.py 创建）")
        return
    print(f"{'租户':<12}{'每日token':<12}{'存储节点上限':<12}")
    print("-" * 40)
    for t in tenants:
        print(f"{t['_id']:<12}{t.get('quota_tokens_per_day', 0):<12}{t.get('quota_storage_nodes', 0):<12}")


if __name__ == "__main__":
    main()
