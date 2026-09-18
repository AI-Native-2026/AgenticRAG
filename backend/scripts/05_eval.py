"""脚本 05：RAG 系统评测（对应学习手册 07 篇）。

用法：python scripts/05_eval.py [--limit 5]

评测维度（大规模 RAG 上线前必做）：
  [检索质量] Hit Rate   : 黄金文档是否出现在召回 top-k 中
             MRR        : 黄金文档的排名倒数均值（越靠前越好）
  [生成质量] faithfulness: 回答是否忠实于检索到的内容（LLM 当裁判）
             relevance   : 回答是否回答了用户问题（LLM 当裁判）
评测集：data/eval_set.jsonl（query + golden_docs + golden_keywords）
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core.llms import ChatMessage  # noqa: E402

from src.llm.gateway import LLMGateway, build_embed_model, setup_settings  # noqa: E402
from src.retrieval.hybrid import HybridRetriever  # noqa: E402
from src.storage.cache import CacheClient  # noqa: E402
from src.storage.docstore import MongoDocStore  # noqa: E402
from src.storage.vector_store import ChromaVectorStore  # noqa: E402


def load_eval_set(path: Path):
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def build_hybrid():
    setup_settings()
    embed = build_embed_model()
    ds = MongoDocStore()
    vs = ChromaVectorStore()
    hybrid = HybridRetriever(embed_model=embed, vector_store=vs)
    hybrid.build_bm25(ds.get_all_nodes())
    return hybrid


def hit_rate_mrr(hybrid, query, golden_docs, top_k=5):
    """在召回结果中统计 Hit Rate 与 MRR。"""
    hits = hybrid.retrieve(query, final_top_k=top_k)
    for rank, h in enumerate(hits, start=1):
        doc_name = h.get("metadata", {}).get("doc_name", "")
        if doc_name in golden_docs:
            return 1.0, 1.0 / rank
    return 0.0, 0.0


def llm_judge(question, answer, golden_keywords):
    """用 LLM 当裁判：判断回答是否命中关键信息（rough faithfulness/relevance）。"""
    llm = LLMGateway().build_llm()
    prompt = (
        f"你是 RAG 评测裁判。请判断下面这个回答是否准确回答了问题，"
        f"并包含这些关键信息: {golden_keywords}。\n"
        f"问题: {question}\n回答: {answer}\n"
        f"只输出 YES 或 NO。"
    )
    resp = str(llm.complete(prompt)).strip().upper()
    return 1.0 if "YES" in resp else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--all", action="store_true", help="跑全部评测题（--limit 覆盖）")
    parser.add_argument("--out", default=None, help="把聚合指标写成 json（建立基线用）")
    args = parser.parse_args()

    eval_set = load_eval_set(PROJECT_ROOT / "data" / "eval_set.jsonl")
    limit = len(eval_set) if args.all else min(args.limit, len(eval_set))
    print(f"评测集共 {len(eval_set)} 题，本次跑 {limit} 题")
    hybrid = build_hybrid()
    llm = LLMGateway().build_llm()

    total_hr = total_mrr = total_f = 0.0
    count = 0
    for item in eval_set[:limit]:
        q = item["query"]
        golden = item["golden_docs"]

        # 1. 检索质量
        hr, mrr = hit_rate_mrr(hybrid, q, golden)
        total_hr += hr
        total_mrr += mrr

        # 2. 生成质量：先取 top3 拼进上下文，让 LLM 回答
        hits = hybrid.retrieve(q, final_top_k=3)
        ctx = "\n\n".join(f"[{h.get('metadata', {}).get('doc_name', '')}]\n{h['text']}" for h in hits)
        answer = str(llm.chat([ChatMessage(role="user", content=f"基于以下资料回答问题：\n{ctx}\n\n问题：{q}")]))
        f = llm_judge(q, answer, item["golden_keywords"])
        total_f += f

        count += 1
        print(f"\n[{count}] Q: {q}")
        print(f"     HitRate={hr} MRR={mrr:.3f} Faithfulness(粗判)={f}")

    summary = {
        "hit_rate": round(total_hr / count, 4),
        "mrr": round(total_mrr / count, 4),
        "answer_hit": round(total_f / count, 4),
        "n": count,
    }
    print("\n" + "=" * 60)
    print(f"HitRate={summary['hit_rate']:.2f} | MRR={summary['mrr']:.3f} | AnswerHit={summary['answer_hit']:.2f}")
    if args.out:
        out_path = PROJECT_ROOT / args.out
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"指标已写入 {out_path}（check_regression.py 用）")
    print("=" * 60)


if __name__ == "__main__":
    main()
