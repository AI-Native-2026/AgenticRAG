"""元数据过滤工具（对应学习手册 04 篇）。

作用：
1. 把高层语义的过滤条件翻译成 Chroma 的 where 语法
2. 多租户强制过滤：无论调用方传不传 tenant，检索时都强制带上，
   防止越权访问其他租户数据（安全教学点）
"""

from typing import Any, Dict, Optional


def build_chroma_where(
    tenant: Optional[str] = None,
    doc_type: Optional[str] = None,
    doc_name: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 Chroma where 条件。所有条件 AND 合并。

    教学点：Chroma 的 where 只支持 $eq/$ne/$in/$gt/$lt 等简单操作符，
    复杂过滤建议回真相源(Mongo)做。
    """
    clauses: Dict[str, Any] = {}
    if tenant:
        clauses["tenant"] = tenant
    if doc_type:
        clauses["doc_type"] = doc_type
    if doc_name:
        clauses["doc_name"] = doc_name
    if extra:
        for k, v in extra.items():
            clauses[k] = v
    return clauses or None


def enforce_tenant_filter(where: Optional[Dict[str, Any]], required_tenant: Optional[str]) -> Dict[str, Any]:
    """强制注入租户条件（防越权）。要求调用方显式声明租户。"""
    if not required_tenant:
        raise ValueError("多租户场景必须显式指定 tenant，防止越权检索")
    where = dict(where or {})
    where["tenant"] = required_tenant
    return where


if __name__ == "__main__":
    w = build_chroma_where(tenant="tech", doc_type="md")
    print("where =", w)
    print("强制过滤后 =", enforce_tenant_filter(w, "tech"))
