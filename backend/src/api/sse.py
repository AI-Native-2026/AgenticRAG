"""SSE（Server-Sent Events）工具（对应 v2 手册 01 篇）。

为什么用 SSE 而不是 WebSocket：
  RAG 回答是「服务端→客户端」单向流，SSE 用 HTTP 长连接天然支持，
  实现简单、有自动重连、无需维护双向连接。WebSocket 适合双向实时
  交互（如聊天打断重问），这里不需要。

P0 方案（规避 v1 的 openai_like 流式 bug）：
  SSE 只做传输层，内部生成仍走非流式的 agent.run()（完整答案一次返回），
  但通过分段事件把「进度/答案/结束」逐步推给客户端：
    event: start   data: {"request_id": ...}
    event: answer  data: {"content": ...}    # 完整答案
    event: done    data: {"request_id": ...}
  （token 级流式留作 v2 后续，依赖 llama-index 升级后补。）
"""

import json
from typing import Any, AsyncIterator, Dict


def sse_event(event: str, data: Dict[str, Any]) -> str:
    """按 SSE 协议格式拼一段事件：
    event: <name>
    data: <json>
    <空行>
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def sse_sequence(events: list) -> AsyncIterator[str]:
    """把一组 (event, data) 依次 yield 成 SSE 流。"""
    for event, data in events:
        yield sse_event(event, data)
