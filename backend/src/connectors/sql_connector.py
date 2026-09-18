"""关系型数据库连接器（基于 SQLAlchemy）。

支持：mysql / postgresql / sqlite / mssql / oracle
能力：
  - discover/describe：抽取表结构与样例（供 Text-to-SQL 与前端 Schema 树）
  - read：按表读取为 RawDocument（支持增量水位线）
  - live_query：Text-to-SQL 实时查询（只读 + 白名单 + LIMIT + 超时）
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from src.connectors.base import (
    BaseConnector, ConnectorError, RawDocument, ResourceMeta, SchemaInfo, register,
)

_DRIVERS = {
    "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql",
    "postgresql": "postgresql+psycopg2",
    "postgres": "postgresql+psycopg2",
    "sqlite": "sqlite",
    "mssql": "mssql+pyodbc",
    "oracle": "oracle+cx_oracle",
}


def build_url(dialect: str, config: Dict[str, Any], credentials: Dict[str, str]) -> str:
    d = _DRIVERS.get(dialect)
    if not d:
        raise ConnectorError(f"不支持的数据库类型：{dialect}")
    if d == "sqlite":
        return f"sqlite:///{config.get('path') or config.get('database') or ':memory:'}"
    user = credentials.get("username", "")
    pwd = credentials.get("password", "")
    host = config.get("host", "localhost")
    port = config.get("port")
    db = config.get("database", "")
    auth = f"{user}:{pwd}@" if user else ""
    hostport = f"{host}:{port}" if port else host
    return f"{d}://{auth}{hostport}/{db}"


@register("mysql")
@register("postgresql")
@register("postgres")
@register("sqlite")
@register("mssql")
@register("oracle")
@register("mariadb")
class SQLConnector(BaseConnector):
    type = "database"
    subtype = "sql"
    capabilities = ("discover", "read", "describe", "live_query")

    def __init__(self, datasource, credentials=None):
        super().__init__(datasource, credentials)
        self.subtype = self.config.get("dialect") or datasource.get("subtype") or "sqlite"
        self._engine = None

    # ---------- 引擎 ----------

    @property
    def engine(self):
        if self._engine is None:
            try:
                from sqlalchemy import create_engine
            except ImportError as e:  # noqa: BLE001
                raise ConnectorError("需要 sqlalchemy：pip install sqlalchemy") from e
            url = build_url(self.subtype, self.config, self.credentials)
            self._engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def test_connection(self) -> Tuple[bool, str]:
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, f"连接成功（{self.subtype}）"
        except Exception as e:  # noqa: BLE001
            return False, f"连接失败：{type(e).__name__}: {e}"

    # ---------- 发现 ----------

    def _allowed_tables(self, inspector) -> List[str]:
        all_tables = inspector.get_table_names()
        allow = self.config.get("tables") or []
        if allow:
            return [t for t in all_tables if t in set(allow)]
        return all_tables

    def discover(self) -> List[ResourceMeta]:
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        out: List[ResourceMeta] = []
        for t in self._allowed_tables(inspector):
            try:
                cols = [c["name"] for c in inspector.get_columns(t)]
            except Exception:  # noqa: BLE001
                cols = []
            out.append(ResourceMeta(name=t, kind="table", columns=cols))
        return out

    def describe(self, resource: str) -> SchemaInfo:
        from sqlalchemy import inspect, text
        inspector = inspect(self.engine)
        cols = []
        for c in inspector.get_columns(resource):
            cols.append({
                "name": c["name"],
                "type": str(c.get("type", "")),
                "nullable": bool(c.get("nullable", True)),
                "pk": bool(c.get("primary_key", False)),
            })
        ddl_cols = ", ".join(f"{c['name']} {c['type']}" for c in cols)
        ddl = f"CREATE TABLE {resource} ({ddl_cols});"
        sample: List[Dict[str, Any]] = []
        row_count = 0
        try:
            with self.engine.connect() as conn:
                res = conn.execute(text(f'SELECT * FROM {self._quote(resource)} LIMIT 5'))
                sample = [dict(r._mapping) for r in res]
                row_count = conn.execute(
                    text(f'SELECT COUNT(*) FROM {self._quote(resource)}')
                ).scalar() or 0
        except Exception:  # noqa: BLE001
            pass
        return SchemaInfo(name=resource, columns=cols, ddl=ddl,
                          sample_rows=sample, row_count=int(row_count))

    # ---------- 读取（同步入库） ----------

    def read(self, resource: Optional[str] = None, watermark: Any = None,
             limit: Optional[int] = None) -> Iterator[RawDocument]:
        from sqlalchemy import text
        tables = [resource] if resource else [m.name for m in self.discover()]
        wm_col = self.config.get("watermark_column")
        for table in tables:
            try:
                info = self.describe(table)
            except Exception:  # noqa: BLE001
                info = SchemaInfo(name=table)
            pk = next((c["name"] for c in info.columns if c.get("pk")),
                      (info.columns[0]["name"] if info.columns else None))
            sql = f"SELECT * FROM {self._quote(table)}"
            params: Dict[str, Any] = {}
            if wm_col and watermark is not None:
                sql += f" WHERE {self._quote(wm_col)} > :wm"
                params["wm"] = watermark
            if wm_col:
                sql += f" ORDER BY {self._quote(wm_col)} ASC"
            if limit:
                sql += f" LIMIT {int(limit)}"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                for i, row in enumerate(result):
                    rec = dict(row._mapping)
                    text_repr = "\n".join(f"{k}: {v}" for k, v in rec.items())
                    yield RawDocument(
                        ref=f"{table}:{rec.get(pk, i) if pk else i}",
                        text=text_repr,
                        title=f"{table} #{rec.get(pk, i) if pk else i}",
                        metadata={
                            "source_type": "database",
                            "datasource_id": self.ds_id,
                            "table": table,
                            "row_id": str(rec.get(pk, i) if pk else i),
                            "doc_name": table,
                            "doc_type": "table_row",
                            "page": 1,
                        },
                    )

    # ---------- 实时查询 ----------

    def live_query(self, question: str, schema_text: str = "", **kwargs) -> Dict[str, Any]:
        from src.connectors.text2sql import generate_sql, run_readonly
        allowed = self.config.get("tables") or None
        sql = generate_sql(question, schema_text, dialect=self.subtype, allowed_tables=allowed)
        result = run_readonly(self.engine, sql, allowed_tables=allowed,
                              timeout=int(self.config.get("timeout", 5)),
                              max_rows=int(self.config.get("max_rows", 200)))
        result["sql"] = sql
        return result

    # ---------- 预览（列名感知脱敏） ----------

    def preview(self, resource: Optional[str] = None, limit: int = 10,
                max_chars: int = 2000) -> List[RawDocument]:
        from sqlalchemy import text as _text

        from src.config import get_env
        from src.connectors.masking import mask_table_rows, row_to_text

        env = get_env()
        mask_on = bool(env.get("PII_MASK_ENABLED", True))
        pats = env.get("PII_MASK_COLUMNS")
        tables = [resource] if resource else [m.name for m in self.discover()]
        out: List[RawDocument] = []
        for table in tables:
            try:
                with self.engine.connect() as conn:
                    res = conn.execute(_text(
                        f"SELECT * FROM {self._quote(table)} LIMIT {int(limit)}"))
                    rows = [dict(r._mapping) for r in res]
            except Exception as e:  # noqa: BLE001
                raise ConnectorError(f"预览失败 {table}: {e}") from e
            if mask_on:
                rows = mask_table_rows(rows, pats)
            for i, row in enumerate(rows):
                out.append(RawDocument(
                    ref=f"{table}#{i}", text=row_to_text(row)[:max_chars], title=table,
                    metadata={"source_type": "database", "datasource_id": self.ds_id,
                              "table": table, "modality": "table", "masked": mask_on},
                ))
                if len(out) >= limit:
                    return out
        return out

    @staticmethod
    def _quote(name: str) -> str:
        if not name.replace("_", "").replace(".", "").isalnum():
            raise ConnectorError(f"非法标识符：{name}")
        return name
