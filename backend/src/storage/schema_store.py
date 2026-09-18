"""表结构元数据（供 Text-to-SQL 做 schema 注入）。

表：agentic_rag.table_schemas
  {_id: "<ds_id>:<table>", datasource_id, tenant, table, columns: [{name,type,nullable,pk}],
   ddl, sample_rows: [], row_count, description, updated_at}
"""

import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.config import get_env


class SchemaStore:
    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        env = get_env()
        import pymongo

        self.client = pymongo.MongoClient(uri or env["MONGO_URI"], serverSelectionTimeoutMS=5000)
        self.db = self.client[db_name or env["MONGO_DB"]]
        self.col = self.db["table_schemas"]
        self.col.create_index("datasource_id")

    def upsert(self, datasource_id: str, table: str, tenant: str,
               columns: List[Dict[str, Any]], ddl: str = "",
               sample_rows: Optional[List[Dict[str, Any]]] = None,
               row_count: int = 0, description: str = "") -> None:
        key = f"{datasource_id}:{table}"
        self.col.replace_one({"_id": key}, {
            "_id": key,
            "datasource_id": datasource_id,
            "tenant": tenant,
            "table": table,
            "columns": columns,
            "ddl": ddl,
            "sample_rows": sample_rows or [],
            "row_count": row_count,
            "description": description,
            "updated_at": time.time(),
        }, upsert=True)

    def list(self, datasource_id: str) -> List[Dict[str, Any]]:
        return list(self.col.find({"datasource_id": datasource_id}).sort("table", 1))

    def get(self, datasource_id: str, table: str) -> Optional[Dict[str, Any]]:
        return self.col.find_one({"_id": f"{datasource_id}:{table}"})

    def clear(self, datasource_id: str) -> None:
        self.col.delete_many({"datasource_id": datasource_id})

    def build_prompt_schema(self, datasource_id: str, max_tables: int = 40) -> str:
        """把表结构拼成适合注入 LLM 的紧凑文本。"""
        lines: List[str] = []
        for t in self.list(datasource_id)[:max_tables]:
            cols = ", ".join(f"{c['name']} {c.get('type', '')}" for c in t.get("columns", []))
            lines.append(f"TABLE {t['table']} ({cols})")
            for row in (t.get("sample_rows") or [])[:2]:
                lines.append(f"  -- sample: {row}")
        return "\n".join(lines)
