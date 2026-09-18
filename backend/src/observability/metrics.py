"""指标聚合：把事件变成数字看板。

从事件里算什么（生产最关心的几个问题）：
  1. 延迟：检索 / 重排 / 生成的 p50、p95
  2. 成本：每租户每天 token 消耗（LLM 账单来源）
  3. 缓存：语义缓存命中率（降本效果的核心指标）
  4. 行为：工具调用次数、配额拒绝次数

为什么自己写而不是用 Prometheus：
  教学场景 Prometheus 是重依赖（服务端 + 采集 + 存储）。这里用
  「事件文件 + 聚合函数」得到同样的数字，原理完全一致，
  换 Prometheus 时只需把 events 变成 metrics 上报即可。
"""

import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 允许直接 python src/xx.py 运行


def _pct(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])  # 单样本：quantiles 要求至少 2 个数据点
    return float(statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1])


def aggregate(events: List[Dict[str, Any]], metering: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把事件列表聚合成指标字典。events 来自 sink.read_all()。

    metering 可选：传入 Metering().daily_usage() 结果，token 成本
    以权威计量为准（事件里的 token 可能因记录点差异不完整）。
    """
    # 按类型分桶
    by_type: Dict[str, List[float]] = defaultdict(list)
    tool_calls: Dict[str, int] = defaultdict(int)
    semantic_hits = semantic_misses = 0
    quota_denied = 0

    for e in events:
        ev_type = e.get("event_type")
        tenant = e.get("tenant") or "unknown"

        if e.get("duration_ms") is not None:
            by_type[ev_type].append(e["duration_ms"])

        if ev_type == "tool_call":
            tool_calls[e.get("tool", "?")] += 1
        elif ev_type == "retrieval":
            if e.get("cache_hit"):
                semantic_hits += 1
            else:
                semantic_misses += 1
        elif ev_type == "quota_denied":
            quota_denied += 1

    # 语义缓存命中率 = 命中 / (命中 + 未命中)，分母为 0 时记为 0
    total_cache = semantic_hits + semantic_misses
    hit_rate = round(semantic_hits / total_cache, 4) if total_cache else 0.0

    # token 成本：优先取权威计量（metering），否则退回事件聚合
    if metering:
        tokens_by_tenant = metering.get("by_tenant", {})
        total_tokens = metering.get("total_prompt", 0) + metering.get("total_completion", 0)
    else:
        tokens_by_tenant = {}
        total_tokens = 0
        for e in events:
            if e.get("event_type") == "generate":
                t = e.get("tenant") or "unknown"
                tokens_by_tenant.setdefault(t, {"prompt": 0, "completion": 0})
                tokens_by_tenant[t]["prompt"] += e.get("prompt_tokens", 0)
                tokens_by_tenant[t]["completion"] += e.get("completion_tokens", 0)
                total_tokens += e.get("prompt_tokens", 0) + e.get("completion_tokens", 0)

    return {
        "request_count": sum(1 for e in events if e.get("event_type") == "request_end"),
        "latency_p50": {t: round(_pct(v, 50), 1) for t, v in by_type.items()},
        "latency_p95": {t: round(_pct(v, 95), 1) for t, v in by_type.items()},
        "tool_calls": dict(tool_calls),
        "tokens_by_tenant": tokens_by_tenant,
        "total_tokens": total_tokens,
        "semantic_cache_hit_rate": hit_rate,
        "quota_denied_count": quota_denied,
    }


def format_report(metrics: Dict[str, Any]) -> str:
    """把指标渲染成人类可读的报表（admin CLI 直接打印）。"""
    lines = ["=" * 50, "Agentic RAG 运行报表", "=" * 50]
    lines.append(f"请求数: {metrics['request_count']}")
    lines.append(f"\n[延迟 p50/p95 ms]")
    for t, v in metrics["latency_p95"].items():
        lines.append(f"  {t:<12} p50={metrics['latency_p50'].get(t, 0):>8}  p95={v:>8}")
    lines.append(f"\n[工具调用]")
    for t, c in metrics["tool_calls"].items():
        lines.append(f"  {t}: {c}")
    lines.append(f"\n[Token 消耗（成本）]")
    for tenant, t in metrics["tokens_by_tenant"].items():
        lines.append(f"  {tenant:<10} prompt={t['prompt']:>8}  completion={t['completion']:>8}")
    lines.append(f"\n[语义缓存命中率] {metrics['semantic_cache_hit_rate']:.2%}")
    lines.append(f"[配额拒绝] {metrics['quota_denied_count']}")
    return "\n".join(lines)


if __name__ == "__main__":
    from src.observability.sink import get_sink

    evts = get_sink().read_all(days=1)
    print(f"读取到 {len(evts)} 条事件")
    if evts:
        print(format_report(aggregate(evts)))
    else:
        print("暂无事件（跑一次 04_agent.py 后再看）")
