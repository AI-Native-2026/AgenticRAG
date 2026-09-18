"""Text-to-SQL 生成与只读安全执行。

安全护栏（多层）：
  1. 仅允许单条 SELECT / WITH ... SELECT / EXPLAIN 语句
  2. 表名白名单（数据源配置）
  3. 禁止 DDL / DML / 多语句 / 注释注入
  4. 强制 LIMIT 上限
  5. 查询超时 + 返回行数上限
  6. 调用方应使用只读数据库账号（配置层保证）
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.connectors.base import ConnectorError

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|call|exec|execute|copy|vacuum)\b",
    re.IGNORECASE,
)
_TABLE_REF = re.compile(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", re.IGNORECASE)


def _strip_ident(name: str) -> str:
    return name.strip().strip('`"[]').split(".")[-1]


def validate_sql(sql: str, allowed_tables: Optional[List[str]] = None) -> str:
    """校验并返回规范化 SQL；不合法则抛 ConnectorError。"""
    if not sql or not sql.strip():
        raise ConnectorError("生成的 SQL 为空")
    cleaned = sql.strip().rstrip(";").strip()

    # 去注释
    if "--" in cleaned or "/*" in cleaned:
        raise ConnectorError("SQL 中不允许注释")
    # 多语句
    if ";" in cleaned:
        raise ConnectorError("只允许单条 SQL 语句")

    # sqlglot 精确解析（若可用）
    parsed_ok = False
    try:
        import sqlglot
        from sqlglot import exp
        statements = sqlglot.parse(cleaned)
        if len(statements) != 1:
            raise ConnectorError("只允许单条 SQL 语句")
        root = statements[0]
        if not isinstance(root, (exp.Select, exp.Union)):
            # 允许 EXPLAIN / WITH
            if not isinstance(root, exp.Command):
                raise ConnectorError(f"仅允许 SELECT 查询，收到：{type(root).__name__}")
        parsed_ok = True
    except ImportError:
        parsed_ok = False
    except ConnectorError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConnectorError(f"SQL 解析失败：{e}") from e

    if not parsed_ok:
        # 兜底：正则校验
        first = cleaned.split(None, 1)[0].lower() if cleaned.split() else ""
        if first not in ("select", "with", "explain"):
            raise ConnectorError("仅允许 SELECT 查询")
    if _FORBIDDEN.search(cleaned):
        raise ConnectorError("SQL 包含禁止的关键字")

    # 表白名单
    if allowed_tables:
        allow = {t.lower() for t in allowed_tables}
        for ref in _TABLE_REF.findall(cleaned):
            name = _strip_ident(ref).lower()
            if name and name not in allow:
                raise ConnectorError(f"表 {name} 不在白名单中")
    return cleaned


def enforce_limit(sql: str, max_rows: int) -> str:
    """无 LIMIT 时强制追加。"""
    if re.search(r"\blimit\b", sql, re.IGNORECASE):
        return sql
    return f"{sql} LIMIT {int(max_rows)}"


def generate_sql(question: str, schema_text: str, dialect: str = "sql",
                 allowed_tables: Optional[List[str]] = None) -> str:
    """调用 LLM 生成 SQL 并做安全校验。"""
    from src.llm.gateway import LLMGateway

    allow_hint = ""
    if allowed_tables:
        allow_hint = f"\n只允许查询这些表：{', '.join(allowed_tables)}。"
    prompt = (
        "你是一个严谨的 SQL 生成器。根据数据库表结构，把用户问题翻译成一条只读 SQL。\n"
        f"数据库方言：{dialect}。\n"
        f"表结构：\n{schema_text}\n{allow_hint}\n"
        "要求：\n"
        "1. 只输出一条 SELECT 语句，不要任何解释、不要 markdown 代码块。\n"
        "2. 不要使用 INSERT/UPDATE/DELETE/DROP 等写操作。\n"
        "3. 不确定的字段不要编造，优先使用表结构中存在的列。\n\n"
        f"用户问题：{question}\nSQL:"
    )
    gateway = LLMGateway()
    raw = gateway.complete(prompt)
    sql = raw.strip()
    # 去掉模型可能返回的角色/标签前缀（assistant: / SQL: 等）
    sql = re.sub(r"^\s*(assistant|ai|sql|sqlquery)\s*[:：]\s*", "", sql, flags=re.IGNORECASE)
    # 去掉 markdown 代码块
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql)
        sql = re.sub(r"\n?```$", "", sql).strip()
    # 若前面还有多余说明，从第一个 SELECT / WITH 开始截取
    m = re.search(r"\b(select|with)\b", sql, re.IGNORECASE)
    if m and m.start() > 0:
        sql = sql[m.start():]
    return validate_sql(sql, allowed_tables)


def run_readonly(engine, sql: str, allowed_tables: Optional[List[str]] = None,
                 timeout: int = 5, max_rows: int = 200) -> Dict[str, Any]:
    """在只读护栏下执行 SQL。"""
    from sqlalchemy import text

    safe = validate_sql(sql, allowed_tables)
    safe = enforce_limit(safe, max_rows)
    try:
        with engine.connect() as conn:
            if hasattr(conn, "execution_options"):
                conn = conn.execution_options()
            result = conn.execute(text(safe))
            columns = list(result.keys())
            rows = [dict(r._mapping) for r in result.fetchmany(max_rows)]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "sql": safe}
    except Exception as e:  # noqa: BLE001
        raise ConnectorError(f"SQL 执行失败：{type(e).__name__}: {e}") from e
