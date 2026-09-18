"""事件模型（观测的核心数据结构）。

一次用户请求的生命周期里，会依次发出多类事件，全部用同一个 request_id 串起来：

  request_start
   ├─ retrieval   (混合检索耗时 + 召回数量)
   ├─ rerank      (重排耗时 + 候选数)
   ├─ tool_call   (Agent 每次调用工具: kb_search / calculator ...)
   ├─ generate    (LLM 生成: prompt_tokens / completion_tokens)
  request_end

为什么需要事件而不是只打日志：
  日志是"打给人看"的，事件是"打给指标算的"。事件有固定 schema，
  聚合脚本才能按 request_id 分组、按字段求和/算分位。
"""

import json
import time
import uuid
from typing import Any, Dict, Optional

# 事件类型白名单（约束 schema，防随手乱写字段）
EVENT_TYPES = {
    "request_start", "retrieval", "rerank", "generate",
    "tool_call", "request_end", "ingest_doc", "quota_denied",
}


def new_request_id() -> str:
    """生成链路追踪 id：一段随机 uuid，串起一次请求的所有事件。"""
    return "req-" + uuid.uuid4().hex[:16]


def make_event(
    event_type: str,
    request_id: str,
    tenant: Optional[str] = None,
    duration_ms: Optional[float] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """构造一条标准事件。event_type 必须在白名单内。"""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"未知事件类型: {event_type}，白名单={EVENT_TYPES}")
    evt: Dict[str, Any] = {
        "ts": time.time(),
        "request_id": request_id,
        "event_type": event_type,
        "tenant": tenant,
        "duration_ms": duration_ms,
    }
    evt.update(extra)
    return evt


def to_json(evt: Dict[str, Any]) -> str:
    """序列化为一行 JSON（jsonl 的 'l' 就是这么来的）。"""
    return json.dumps(evt, ensure_ascii=False, default=str)
