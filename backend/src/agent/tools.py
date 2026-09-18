"""Agent 工具集（知识中台版）。

在 v2 治理（权限 + 审计）基础上扩展数据接入能力：
  知识检索：kb_search / kb_search_by_tenant
  数据库：  list_datasources / describe_table / sql_query
  通用：    calculator

安全要点：
  - tenant 一律取自线程本地 _CTX（由 API 从 JWT 注入），不信任 LLM 传参，
    防止模型被诱导跨租户检索。
  - sql_query 走 Text-to-SQL 安全护栏（只读 / 白名单 / LIMIT / 超时）。
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llama_index.core.tools import FunctionTool

from src.agent.registry import get_registry
from src.observability.events import make_event
from src.observability.sink import get_sink
from src.storage.audit import AuditLog
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.rerank import Reranker


import contextvars


class RequestContext:
    """当前请求上下文（role / request_id / tenant / emit）。

    使用 contextvars 而非 threading.local：Agent 的工具可能在 asyncio 的
    工作线程中执行，contextvars 会自动随上下文传播，threading.local 不会。
    """

    def __init__(self):
        self._role = contextvars.ContextVar("ctx_role", default="member")
        self._rid = contextvars.ContextVar("ctx_rid", default="unknown")
        self._tenant = contextvars.ContextVar("ctx_tenant", default=None)
        self._emit = contextvars.ContextVar("ctx_emit", default=None)
        self._datasources = contextvars.ContextVar("ctx_datasources", default=None)
        self._kbs = contextvars.ContextVar("ctx_kbs", default=None)

    @property
    def role(self):
        return self._role.get()

    @property
    def request_id(self):
        return self._rid.get()

    @property
    def tenant(self):
        return self._tenant.get()

    @property
    def emit(self):
        return self._emit.get()

    @property
    def datasource_ids(self):
        return self._datasources.get()

    @property
    def kb_ids(self):
        return self._kbs.get()


_CTX = RequestContext()


def set_ctx(role: str, request_id: str, tenant: Optional[str] = None, emit=None,
            datasource_ids: Optional[List[str]] = None,
            kb_ids: Optional[List[str]] = None) -> None:
    _CTX._role.set(role)
    _CTX._rid.set(request_id)
    _CTX._tenant.set(tenant)
    _CTX._emit.set(emit)
    _CTX._datasources.set(datasource_ids)
    _CTX._kbs.set(kb_ids)


def clear_ctx() -> None:
    _CTX._role.set("member")
    _CTX._rid.set("unknown")
    _CTX._tenant.set(None)
    _CTX._emit.set(None)
    _CTX._datasources.set(None)
    _CTX._kbs.set(None)


def emit_step(event_type: str, **data) -> None:
    """向当前请求的事件回调推送一个流式步骤（供 SSE 使用）。"""
    cb = _CTX.emit
    if cb:
        try:
            cb(event_type, data)
        except Exception:  # noqa: BLE001
            pass


class RAGTools:
    """把所有检索/数据组件打包成带治理的工具。"""

    def __init__(self, hybrid: HybridRetriever, reranker: Reranker,
                 datasource_store=None, schema_store=None):
        self.hybrid = hybrid
        self.reranker = reranker
        self.registry = get_registry()
        self.audit = AuditLog()
        self._datasource_store = datasource_store
        self._schema_store = schema_store

    # ---------- 懒加载依赖 ----------

    @property
    def datasource_store(self):
        if self._datasource_store is None:
            from src.storage.datasource_store import DatasourceStore
            self._datasource_store = DatasourceStore()
        return self._datasource_store

    @property
    def schema_store(self):
        if self._schema_store is None:
            from src.storage.schema_store import SchemaStore
            self._schema_store = SchemaStore()
        return self._schema_store

    # ---------- 知识检索 ----------

    def kb_search(self, query: str, top_k: int = 5, kb_id: Optional[str] = None) -> str:
        """在知识库中检索与问题最相关的片段（向量 + 关键词 + 重排）。

        参数：
          query (str): 用户的问题或关键信息
          top_k (int): 返回片段数量，默认 5
          kb_id (str): 可选，限定某个知识库范围
        返回：JSON 数组，每项含 text(内容)、doc_name(来源)、score(相关度)
        """
        request_id = _CTX.request_id
        tenant = _CTX.tenant  # 强制使用 JWT 租户，忽略模型传参
        where: Dict[str, Any] = {}
        if tenant:
            where["tenant"] = tenant
        # 检索范围：用户在对话中选择的知识库（多个取并集）；为空表示全部
        ds_scope = _CTX.datasource_ids
        kb_ids = list(_CTX.kb_ids or [])
        if kb_id and kb_id not in kb_ids:
            kb_ids.append(kb_id)
        if kb_ids:
            union = set()
            for kid in kb_ids:
                kbd = self._get_kb(kid)
                if kbd:
                    union.update(kbd.get("datasource_ids", []))
            ds_scope = list(union)
        if ds_scope:
            where["datasource_id"] = {"$in": list(ds_scope)}
        where = where or None

        t0 = time.time()
        candidates = self.hybrid.retrieve(query, where=where, final_top_k=30)
        dur_recall = (time.time() - t0) * 1000
        t0 = time.time()
        ranked = self.reranker.rerank(query, candidates, top_n=top_k)
        dur_rerank = (time.time() - t0) * 1000

        get_sink().record(make_event("retrieval", request_id=request_id, tenant=tenant,
                                     duration_ms=round(dur_recall, 1), n_candidates=len(candidates)))
        get_sink().record(make_event("rerank", request_id=request_id, tenant=tenant,
                                     duration_ms=round(dur_rerank, 1), n_input=len(candidates)))
        emit_step("retrieval", n_candidates=len(candidates), duration_ms=round(dur_recall, 1))
        emit_step("rerank", n_output=len(ranked), duration_ms=round(dur_rerank, 1))

        return json.dumps(
            [
                {
                    "text": r["text"],
                    "doc_name": r.get("metadata", {}).get("doc_name", ""),
                    "source_type": r.get("metadata", {}).get("source_type", "file"),
                    "node_id": r["node_id"],
                    "score": r.get("rerank_score", r.get("rrf_score", 0)),
                }
                for r in ranked
            ],
            ensure_ascii=False,
        )

    def kb_search_by_tenant(self, tenant: str, query: str, top_k: int = 5) -> str:
        """只在当前租户的知识库中检索（tenant 参数仅作提示，实际以登录租户为准）。"""
        return self.kb_search(query=query, top_k=top_k)

    def _get_kb(self, kb_id: str) -> Optional[Dict[str, Any]]:
        try:
            from src.storage.kb_store import KnowledgeBaseStore
            return KnowledgeBaseStore().get(kb_id)
        except Exception:  # noqa: BLE001
            return None

    # ---------- 数据库工具 ----------

    def list_datasources(self) -> str:
        """列出当前租户已接入的数据源（数据库/文件/Web），返回 id、名称、类型。"""
        tenant = _CTX.tenant
        items = self.datasource_store.list(tenant=tenant)
        return json.dumps(
            [{"datasource_id": d["ds_id"], "name": d["name"], "type": d["type"],
              "subtype": d["subtype"], "status": d["status"]} for d in items],
            ensure_ascii=False,
        )

    def describe_table(self, datasource_id: str, table: str) -> str:
        """查看某个数据库数据源中一张表的字段结构（用于写 SQL 前确认字段）。

        参数：
          datasource_id (str): 数据源 id（先用 list_datasources 获取）
          table (str): 表名
        """
        self._assert_tenant_datasource(datasource_id)
        info = self.schema_store.get(datasource_id, table)
        if not info:
            return json.dumps({"error": f"未找到表 {table} 的结构，请先同步数据源"}, ensure_ascii=False)
        return json.dumps({
            "table": info["table"],
            "columns": info.get("columns", []),
            "ddl": info.get("ddl", ""),
            "sample_rows": info.get("sample_rows", []),
            "row_count": info.get("row_count", 0),
        }, ensure_ascii=False)

    def sql_query(self, datasource_id: str, question: str) -> str:
        """对某个数据库数据源用自然语言实时查询（Text-to-SQL，只读）。

        参数：
          datasource_id (str): 数据源 id（先用 list_datasources 获取）
          question (str): 自然语言问题，如 "订单表里有多少条已支付记录"
        返回：JSON，含 sql、columns、rows
        """
        ds = self._assert_tenant_datasource(datasource_id)
        from src.ingestion.sync import SyncService
        connector = SyncService.build_connector(ds)
        try:
            schema_text = self.schema_store.build_prompt_schema(datasource_id)
            if not schema_text:
                try:
                    SyncService.build_connector(ds)
                    self._extract_schema(ds, connector)
                    schema_text = self.schema_store.build_prompt_schema(datasource_id)
                except Exception:  # noqa: BLE001
                    pass
            result = connector.live_query(question, schema_text=schema_text)
            result["rows"] = _jsonable(result.get("rows", []))
            emit_step("sql", sql=result.get("sql", ""), row_count=result.get("row_count", 0))
            return json.dumps(result, ensure_ascii=False)
        finally:
            connector.close()

    def _extract_schema(self, ds: Dict[str, Any], connector) -> None:
        from src.ingestion.sync import SyncService
        SyncService(
            embed_model=None, docstore=None, vector_store=None, index_store=None,
            schema_store=self.schema_store,
        ).extract_schema(ds, connector)

    def _assert_tenant_datasource(self, datasource_id: str) -> Dict[str, Any]:
        """确保数据源存在且属于当前租户（越权防御）。"""
        ds = self.datasource_store.get(datasource_id)
        if not ds:
            raise ValueError(f"数据源不存在：{datasource_id}")
        tenant = _CTX.tenant
        if tenant and ds.get("tenant") != tenant:
            raise PermissionError("无权访问其他租户的数据源")
        return ds

    # ---------- 通用 ----------

    def calculator(self, expression: str) -> str:
        """计算数学表达式（如 '2 + 3 * 4'）。检索到数字后常用。"""
        import ast
        import operator

        ops = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow,
        }

        def _eval(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp):
                return ops[type(node.op)](_eval(node.left), _eval(node.right))
            raise ValueError("不支持的表达式")

        result = _eval(ast.parse(expression, mode="eval").body)
        return f"{expression} = {result}"

    # ---------- 治理包装 ----------

    def _wrap(self, name: str, fn, allowed_roles: List[str]) -> Any:
        def wrapped(*args, **kwargs):
            role = _CTX.role
            request_id = _CTX.request_id
            if not self.registry.can_call(name, role):
                self._log_audit(name, request_id, role, args, kwargs, allowed=False)
                raise PermissionError(f"角色 {role} 无权调用工具 {name}")
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                ok = True
            except Exception:
                ok = False
                raise
            finally:
                duration = (time.time() - t0) * 1000
                self.registry.record_call(name)
                self._log_audit(name, request_id, role, args, kwargs,
                                allowed=True, ok=ok, duration_ms=duration)
            return result

        self.registry.register(name, fn, roles=allowed_roles)
        return wrapped

    def _log_audit(self, name, request_id, role, args, kwargs, allowed, ok=True, duration_ms=0):
        self.audit.record(
            tool=name, request_id=request_id, role=role,
            args={"args": str(args)[:200],
                  "kwargs": {k: v for k, v in kwargs.items() if k not in ("request_id", "role")}},
            allowed=allowed, ok=ok, duration_ms=round(duration_ms, 1),
        )
        get_sink().record(make_event(
            "tool_call", request_id=request_id,
            tool=name, role=role, allowed=allowed,
            duration_ms=round(duration_ms, 1),
        ))
        emit_step("tool_call", tool=name, allowed=allowed, ok=ok,
                  duration_ms=round(duration_ms, 1))

    # ---------- 组装 ----------

    def build_tools(self, role: str = "member") -> List[FunctionTool]:
        specs = [
            ("kb_search", self.kb_search, ["member", "admin"]),
            ("kb_search_by_tenant", self.kb_search_by_tenant, ["member", "admin"]),
            ("list_datasources", self.list_datasources, ["member", "admin"]),
            ("describe_table", self.describe_table, ["member", "admin"]),
            ("sql_query", self.sql_query, ["member", "admin"]),
            ("calculator", self.calculator, ["member", "admin"]),
        ]
        tools = []
        for name, fn, roles in specs:
            wrapped = self._wrap(name, fn, allowed_roles=roles)
            tools.append(FunctionTool.from_defaults(fn=wrapped, name=name, description=fn.__doc__))
        return tools


def _jsonable(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
             for k, v in r.items()} for r in rows]
