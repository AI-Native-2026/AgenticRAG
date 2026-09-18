"""敏感数据脱敏（PII）。

在"预览 / 展示"链路对文本做脱敏，满足隐私合规（GDPR/个保法）要求。
注意：脱敏只作用于展示层，不影响已入库的原始数据与检索能力。

支持：手机号、邮箱、身份证、银行卡、IP、护照/自定义正则。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# 顺序敏感：先匹配更长的模式（身份证18 > 银行卡16-19 > 手机号11）
_RULES: List[Tuple[str, re.Pattern, Any]] = [
    ("email", re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"),
     lambda m: f"{m.group(1)}***{m.group(2)}"),
    ("id_card", re.compile(r"(?<!\d)(\d{4})\d{10}(\d{3}[\dXx])(?!\d)"),
     lambda m: f"{m.group(1)}**********{m.group(2)}"),
    ("bank_card", re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)"),
     lambda m: f"{m.group(1)} **** **** {m.group(2)}"),
    ("phone_cn", re.compile(r"(?<!\d)(1[3-9]\d)\d{6}(\d{2})(?!\d)"),
     lambda m: f"{m.group(1)}******{m.group(2)}"),
    ("phone_intl", re.compile(r"(\+\d{1,3}[ -]?)(\d{2})\d{4,8}(\d{2})"),
     lambda m: f"{m.group(1)}{m.group(2)}****{m.group(3)}"),
    ("ipv4", re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b"),
     lambda m: f"{m.group(1)}.{m.group(2)}.*.*"),
    ("passport", re.compile(r"\b([A-Z]\d{3})\d{4,6}\b"),
     lambda m: f"{m.group(1)}****"),
]


def mask_text(text: str, extra_patterns: List[str] | None = None) -> str:
    if not text:
        return text
    out = text
    for _name, pat, repl in _RULES:
        out = pat.sub(repl, out)
    for p in extra_patterns or []:
        try:
            out = re.sub(p, "***", out)
        except re.error:
            continue
    return out


def mask_any(value: Any, extra_patterns: List[str] | None = None) -> Any:
    """递归脱敏：字符串直接脱敏，dict/list 逐项处理，其它原样返回。"""
    if isinstance(value, str):
        return mask_text(value, extra_patterns)
    if isinstance(value, dict):
        return {k: mask_any(v, extra_patterns) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_any(v, extra_patterns) for v in value]
    return value


def mask_rows(rows: List[Dict[str, Any]], extra_patterns: List[str] | None = None) -> List[Dict[str, Any]]:
    return [mask_any(r, extra_patterns) for r in rows]


# ---------- 列名感知脱敏（数据库行） ----------

DEFAULT_SENSITIVE_COLUMNS = [
    "name", "phone", "mobile", "tel", "email", "mail", "id_card", "idcard",
    "id_no", "ssn", "passport", "bank", "card", "account", "address", "addr",
]


def is_sensitive_column(column: str, patterns: List[str] | None = None) -> bool:
    col = str(column).lower()
    for p in (patterns or DEFAULT_SENSITIVE_COLUMNS):
        if p and p in col:
            return True
    return False


def _mask_column_value(column: str, value: Any) -> Any:
    if value is None or value == "":
        return value
    s = str(value)
    col = str(column).lower()
    if any(k in col for k in ("phone", "mobile", "tel")):
        return mask_text(s)
    if any(k in col for k in ("email", "mail")):
        return mask_text(s)
    if any(k in col for k in ("id_card", "idcard", "id_no", "ssn", "passport")):
        return mask_text(s)
    if any(k in col for k in ("bank", "card", "account")):
        return mask_text(s)
    if any(k in col for k in ("address", "addr")):
        return (s[:6] + "***") if len(s) > 6 else "***"
    if "name" in col:
        return (s[0] + "*" * (len(s) - 1)) if len(s) > 1 else "*"
    return mask_text(s)


def mask_row(row: Dict[str, Any], patterns: List[str] | None = None) -> Dict[str, Any]:
    """按列名对一行数据脱敏；非敏感列仍做通用文本脱敏兜底。"""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if is_sensitive_column(k, patterns):
            out[k] = _mask_column_value(k, v)
        else:
            out[k] = mask_text(str(v)) if isinstance(v, str) else v
    return out


def mask_table_rows(rows: List[Dict[str, Any]],
                    patterns: List[str] | None = None) -> List[Dict[str, Any]]:
    return [mask_row(r, patterns) for r in rows]


def row_to_text(row: Dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in row.items() if str(v).strip() != "")


if __name__ == "__main__":
    demo = "张三 13812345678 zhang.san@example.com 110101199003071234 6222021234567890123 192.168.1.100"
    print(mask_text(demo))
