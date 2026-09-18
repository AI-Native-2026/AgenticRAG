"""脚本 04：Agentic RAG 对话演示。

用法：python scripts/04_agent.py
演示三类能力：
  1. 单跳问答：直接检索知识库回答（来源可追溯）
  2. 多跳 + 多工具：检索到两个价格 → 用 calculator 算差价
  3. 多租户隔离：限定 tenant 检索，防止越权
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.agent import AgenticRAG  # noqa: E402
from src.agent.tools import RAGTools  # noqa: E402
from src.llm.gateway import LLMGateway, build_embed_model, setup_settings  # noqa: E402
from src.retrieval.hybrid import HybridRetriever  # noqa: E402
from src.retrieval.rerank import Reranker  # noqa: E402
from src.storage.cache import CacheClient  # noqa: E402
from src.storage.docstore import MongoDocStore  # noqa: E402
from src.storage.vector_store import ChromaVectorStore  # noqa: E402


def build_agent():
    setup_settings()
    embed = build_embed_model()
    ds = MongoDocStore()
    vs = ChromaVectorStore()

    hybrid = HybridRetriever(embed_model=embed, vector_store=vs)
    hybrid.build_bm25(ds.get_all_nodes())

    tools = RAGTools(hybrid, Reranker(backend="cross_encoder")).build_tools()
    llm = LLMGateway().build_llm()
    return AgenticRAG(tools, llm)


def main():
    rag = build_agent()
    agent = rag.build_agent(agent_type="function")
    session_id = "demo-agent-session"

    questions = [
        "iPhone 17 的电池容量是多少，支持多少瓦快充？",
        "特斯拉 Model 3 后驱版和长续航版价格分别是多少？请帮我算出两者的差价。",
        "2026 年三季度北向资金净流入多少亿元？主要流向哪个板块？",
        "你好，还记得我们刚才聊了什么吗？",  # 多轮记忆验证
    ]

    print("=" * 70)
    print("Agentic RAG 演示 —— 输入 exit 退出；每轮问题见代码注释")
    print("=" * 70)

    for q in questions:
        print(f"\n>>> 用户: {q}")
        ans = rag.chat(agent, session_id, q)
        print(f"<<< Agent: {ans}")

    # 交互模式（可选）
    print("\n-------- 进入自由问答（输入 exit 退出）--------")
    while True:
        try:
            q = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() == "exit":
            break
        ans = rag.chat(agent, session_id, q)
        print(f"<<< Agent: {ans}")


if __name__ == "__main__":
    main()
