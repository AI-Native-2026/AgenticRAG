"""运行报表 + 告警检查（v2 admin CLI）。

用法：python scripts/admin/report.py [--days 1]
输出：延迟 p50/p95、工具调用、token 消耗、语义缓存命中率、配额拒绝数、告警结果。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.observability.alerts import check, load_rules  # noqa: E402
from src.observability.metrics import aggregate, format_report  # noqa: E402
from src.observability.sink import get_sink  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    args = parser.parse_args()

    events = get_sink().read_all(days=args.days)
    from src.storage.metering import Metering

    metrics = aggregate(events, metering=Metering().daily_usage(days=args.days))
    print(format_report(metrics))

    hits = check(metrics, load_rules())
    print("\n[告警]")
    if hits:
        for h in hits:
            print(f"  ⚠ {h['name']}: {h['message']} (当前 {h['value']} vs 阈值 {h['threshold']})")
    else:
        print("  无触发，一切正常")


if __name__ == "__main__":
    main()
