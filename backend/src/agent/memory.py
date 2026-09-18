"""会话上下文管理：短期记忆 + 长期摘要压缩。

设计：
  短期记忆 —— 最近 N 轮原文，受 token 预算约束（超预算从最旧开始裁剪）
  长期记忆 —— 超出窗口的旧消息由 LLM 压缩成"会话摘要"，持久化到 MongoDB，
              下一轮以 system 消息形式回注，保证长对话不丢关键信息且不撑爆上下文。

这样既避免"上下文无限增长导致 token 爆炸/超窗"，又保留跨轮次的长期信息。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """轻量 token 估算（中英混排，约 2 字符/token），避免引入 tokenizer 依赖。"""
    if not text:
        return 0
    return max(1, len(text) // 2)


class ContextManager:
    """负责构建送入 Agent 的记忆上下文，并在必要时压缩历史。"""

    def __init__(self, sessions, llm=None):
        env = get_env()
        self.sessions = sessions
        self.llm = llm
        self.token_limit = int(env["MEMORY_TOKEN_LIMIT"])
        self.recent_turns = int(env["MEMORY_RECENT_TURNS"])
        self.summary_enabled = bool(env["MEMORY_SUMMARY_ENABLED"])

    # ---------- 压缩 ----------

    def maybe_compress(self, session_id: str) -> None:
        """当历史超出窗口时，把窗口外的旧消息压缩进会话摘要。"""
        if not self.summary_enabled or self.llm is None:
            return
        hist = self.sessions.history(session_id, limit=1000)
        if not hist:
            return
        rec = self.sessions.get_summary(session_id)
        covered = int(rec.get("covered", 0)) if rec else 0
        keep = self.recent_turns * 2  # 一轮 = user + assistant
        cutoff = max(covered, len(hist) - keep)
        if cutoff <= covered:
            return
        to_summarize = hist[covered:cutoff]
        if not to_summarize:
            return
        prev = rec.get("summary", "") if rec else ""
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)
        prompt = (
            "你是对话摘要器。请把下面的对话历史压缩成简洁的中文要点，保留："
            "用户目标、已确认的事实与数字、未解决的问题、关键结论。"
            "不要编造，不要加入原文没有的信息。\n\n"
            + (f"已有摘要：\n{prev}\n\n" if prev else "")
            + f"新增对话：\n{convo}\n\n合并后的摘要："
        )
        try:
            resp = self.llm.complete(prompt)
            summary = getattr(resp, "text", None) or str(resp)
            self.sessions.set_summary(session_id, summary.strip(), cutoff)
            logger.info("会话 %s 已压缩 %d 条历史消息", session_id, len(to_summarize))
        except Exception as e:  # noqa: BLE001 —— 压缩失败不影响对话
            logger.warning("会话摘要失败: %s", e)

    # ---------- 构建上下文 ----------

    def load_messages(self, session_id: str) -> List[Dict[str, str]]:
        """返回用于恢复记忆的消息列表（摘要 + 预算内最近原文）。"""
        rec = self.sessions.get_summary(session_id)
        covered = int(rec.get("covered", 0)) if rec else 0
        hist = self.sessions.history(session_id, limit=1000)
        recent = hist[covered:]

        selected: List[Dict[str, str]] = []
        total = 0
        for m in reversed(recent):
            t = estimate_tokens(m.get("content", ""))
            if selected and total + t > self.token_limit:
                break
            selected.append(m)
            total += t
        selected.reverse()

        out: List[Dict[str, str]] = []
        if rec and rec.get("summary"):
            out.append({"role": "system", "content": "【历史对话摘要】" + rec["summary"]})
        out.extend(selected)
        return out

    def stats(self, session_id: str) -> Dict[str, Any]:
        rec = self.sessions.get_summary(session_id)
        hist = self.sessions.history(session_id, limit=1000)
        return {
            "messages": len(hist),
            "summarized": int(rec.get("covered", 0)) if rec else 0,
            "has_summary": bool(rec and rec.get("summary")),
            "token_limit": self.token_limit,
        }
