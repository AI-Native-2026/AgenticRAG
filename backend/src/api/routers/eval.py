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
    return {"items": _load_set(), "count": len(_load_set())}


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
