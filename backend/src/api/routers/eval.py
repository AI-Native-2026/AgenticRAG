"""评测路由：评测集、检索指标、基线对比。"""

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Request

from src.api.deps import get_bearer
from src.config import PROJECT_ROOT

router = APIRouter(prefix="/v1/eval", tags=["eval"])

EVAL_FILE = PROJECT_ROOT / "data" / "eval_set.jsonl"
BASELINE_FILE = PROJECT_ROOT / "data" / "baseline.json"


def _load_set() -> List[Dict[str, Any]]:
    if not EVAL_FILE.exists():
        return []
    items = []
    for line in EVAL_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


@router.get("/set")
def get_set(request: Request):
    get_bearer(request)
    items = _load_set()
    return {"items": items, "count": len(items)}


def _save_set(items: List[Dict[str, Any]]) -> None:
    EVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(it, ensure_ascii=False) for it in items]
    EVAL_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


@router.post("/set")
def add_item(request: Request, body: Dict[str, Any]):
    """新增一条评测项：{query, golden_docs[], golden_keywords[]}。"""
    get_bearer(request)
    query = (body.get("query") or "").strip()
    if not query:
        from src.api.deps import AppError
        raise AppError(400, "BAD_REQUEST", "query 不能为空")
    items = _load_set()
    items.append({
        "query": query,
        "golden_docs": body.get("golden_docs") or [],
        "golden_keywords": body.get("golden_keywords") or [],
    })
    _save_set(items)
    return {"count": len(items)}


@router.delete("/set/{index}")
def delete_item(request: Request, index: int):
    get_bearer(request)
    items = _load_set()
    if index < 0 or index >= len(items):
        from src.api.deps import AppError
        raise AppError(404, "NOT_FOUND", "评测项不存在")
    items.pop(index)
    _save_set(items)
    return {"count": len(items)}


@router.post("/run")
def run_eval(request: Request):
    """对评测集执行检索，计算 Hit Rate / MRR（不调用 LLM 裁判）。"""
    get_bearer(request)
    svc = request.app.state.svc
    items = _load_set()
    hits = 0
    rr_sum = 0.0
    details = []
    for it in items:
        query = it.get("query", "")
        golden = set(it.get("golden_docs", []) or [])
        results = svc.hybrid.retrieve(query, final_top_k=10)
        rank = 0
        for i, r in enumerate(results):
            name = (r.get("metadata") or {}).get("doc_name", "")
            if name in golden:
                rank = i + 1
                break
        if rank:
            hits += 1
            rr_sum += 1.0 / rank
        details.append({"query": query, "hit": bool(rank), "rank": rank or None})
    n = len(items) or 1
    report = {
        "count": len(items),
        "hit_rate": round(hits / n, 4),
        "mrr": round(rr_sum / n, 4),
        "details": details,
    }
    return {"report": report}


@router.get("/baseline")
def get_baseline(request: Request):
    get_bearer(request)
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {}


@router.post("/baseline")
def save_baseline(request: Request, body: Dict[str, Any]):
    get_bearer(request)
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True}
