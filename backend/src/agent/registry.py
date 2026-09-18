"""工具注册中心（对应 v2 手册 06 篇）。

为什么需要注册中心而不是直接 `FunctionTool.from_defaults(fn)`：
  工具一多，就会出现"哪个工具谁能用、调没调、调了几次"失控。
  注册中心把工具的三要素集中管理：
    - 能力  ：函数本体 + docstring（给 LLM 看的契约）
    - 权限  ：允许哪些角色调用（roles）
    - 治理  ：调用限流、审计钩子
  生产上这层通常还要接"审批流"：新增工具过审批才上架。
"""

import time
from typing import Any, Callable, Dict, List, Optional


class ToolRegistry:
    def __init__(self):
        # name -> {fn, roles, description, rate_limit_per_min, calls}
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        roles: List[str],
        description: Optional[str] = None,
        rate_limit_per_min: int = 0,  # 0 = 不限
    ) -> None:
        """注册一个工具。roles: ["member","admin",...] 允许调用的角色。"""
        self._tools[name] = {
            "fn": fn,
            "roles": roles,
            "description": description or fn.__doc__ or "",
            "rate_limit_per_min": rate_limit_per_min,
            "registered_at": time.time(),
            "calls": 0,
        }

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    def can_call(self, name: str, role: str) -> bool:
        """权限判断：角色在允许列表里才能调用。"""
        meta = self.get(name)
        if meta is None:
            return False
        return role in meta["roles"]

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": k, "roles": v["roles"], "description": v["description"][:80], "calls": v["calls"]}
            for k, v in self._tools.items()
        ]

    def record_call(self, name: str) -> None:
        if name in self._tools:
            self._tools[name]["calls"] += 1

    def check_rate(self, name: str) -> bool:
        """简易调用限流：按注册时的每分钟上限。0 表示不限。"""
        meta = self.get(name)
        if meta is None or meta["rate_limit_per_min"] <= 0:
            return True
        # 教学简化：以进程运行时间为窗口，calls/分钟 < 上限
        elapsed_min = max((time.time() - meta["registered_at"]) / 60.0, 1.0)
        return meta["calls"] / elapsed_min < meta["rate_limit_per_min"]


# 全局单例：API 进程内只建一个注册中心
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
