"""告警规则引擎。

规则长什么样（data/alerts_rules.json）：
  [{
    "name": "generate_too_slow",
    "metric": "latency_p95.generate",
    "op": "gt",
    "threshold": 15000,
    "window_hours": 24,
    "message": "生成 p95 延迟超 15s，检查 LLM/网络"
  }, ...]

为什么用"规则文件 + 检查脚本"而不是监控平台：
  单机教学场景，一个 `python scripts/admin/check_alerts.py` 就够了——
  它读指标 → 逐条规则判断 → 命中则打印/写告警日志（可接 webhook）。
  原理与 Prometheus + Alertmanager 完全一致：指标 + 规则 + 触发。
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行

from src.config import get_env


def _resolve(metrics: Dict[str, Any], dotted_key: str) -> Any:
    """按 'a.b.c' 从 metrics 字典取值。取不到返回 None。"""
    cur: Any = metrics
    for part in dotted_key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def load_rules(path: str | None = None) -> List[Dict[str, Any]]:
    env = get_env()
    p = Path(path or f"{env['PROJECT_ROOT']}/data/alerts_rules.json")
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def check(metrics: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """逐条规则判断，返回触发的告警列表。"""
    triggered = []
    for rule in rules:
        value = _resolve(metrics, rule["metric"])
        if value is None:
            continue
        op = rule.get("op", "gt")
        threshold = rule["threshold"]
        hit = {
            "gt": value > threshold,
            "lt": value < threshold,
            "ge": value >= threshold,
            "le": value <= threshold,
        }.get(op, False)
        if hit:
            triggered.append({
                "name": rule["name"],
                "metric": rule["metric"],
                "value": value,
                "threshold": threshold,
                "message": rule.get("message", ""),
            })
    return triggered


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.observability.metrics import aggregate, format_report
    from src.observability.sink import get_sink

    evts = get_sink().read_all(days=1)
    metrics = aggregate(evts)
    print(format_report(metrics))
    hits = check(metrics, load_rules())
    print("\n" + "=" * 50)
    if hits:
        for h in hits:
            print(f"[告警] {h['name']}: {h['message']} (当前 {h['value']} {h['threshold']})")
    else:
        print("[告警] 无触发，一切正常")
