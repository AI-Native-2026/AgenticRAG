"""创建租户（v2 admin CLI）。

用法：python scripts/admin/create_tenant.py --tenant tech --tokens 100000 --storage 10000
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.storage.quota import QuotaManager  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--tokens", type=int, default=100000, help="每日 token 预算")
    parser.add_argument("--storage", type=int, default=10000, help="存储节点上限")
    args = parser.parse_args()

    qm = QuotaManager()
    qm.create_tenant(args.tenant, quota_tokens_per_day=args.tokens,
                     quota_storage_nodes=args.storage)
    print(f"租户 {args.tenant} 创建成功: 每日 token={args.tokens}, 存储节点上限={args.storage}")


if __name__ == "__main__":
    main()
