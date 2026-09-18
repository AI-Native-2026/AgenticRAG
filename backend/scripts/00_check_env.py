"""脚本 00：环境自检（每个组件单独验证，跑通才能进入后续步骤）。

用法：python scripts/00_check_env.py
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_env, setup_global_env

OK = "\033[92m[OK]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

setup_global_env()
env = get_env()


def check(name, fn):
    try:
        info = fn()
        print(f"{OK} {name}: {info}")
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} {name}: {e}")
        return False
    return True


def main():
    print("=" * 60)
    print("Agentic RAG 教学示例 —— 环境自检")
    print("=" * 60)

    results = []

    # 1. 配置读取
    results.append(check("配置读取(test.env)", lambda: f"LLM_MODEL={env['LLM_MODEL']}, key={'已配置' if env['DEEPSEEK_API_KEY'] else '缺失'}"))

    # 2. 基础服务
    results.append(check("MongoDB", lambda: "连接成功" if _ping_mongo() else "连接失败"))

    def _ping_redis():
        import redis
        r = redis.Redis.from_url(env["REDIS_URI"], socket_connect_timeout=3)
        return "PONG" if r.ping() else "no pong"
    results.append(check("Redis", _ping_redis))

    # 3. Python 依赖
    def _deps():
        import importlib.metadata

        import chromadb
        import llama_index.core

        return f"llama-index-core {llama_index.core.__version__}, chromadb {chromadb.__version__}"
    results.append(check("核心依赖", _deps))

    # 4. GPU
    def _gpu():
        import torch
        return f"cuda={torch.cuda.is_available()} {torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''}"
    results.append(check("GPU", _gpu))

    # 5. embedding 模型
    def _embed():
        from src.llm.gateway import build_embed_model
        m = build_embed_model()
        v = m.get_text_embedding("测试")
        return f"bge-small-zh dim={len(v)}"
    results.append(check("Embedding(bge-small-zh)", _embed))

    # 6. 重排模型
    def _rerank():
        from src.retrieval.rerank import Reranker
        r = Reranker()
        out = r.rerank("测试", [{"node_id": "x", "text": "测试文本"}], top_n=1)
        return f"bge-reranker-base score={out[0]['rerank_score']}"
    results.append(check("Reranker(bge-reranker)", _rerank))

    # 7. 存储连通
    def _chroma():
        from src.storage.vector_store import ChromaVectorStore
        vs = ChromaVectorStore()
        return f"chroma count={vs.count()}"
    results.append(check("Chroma 向量库", _chroma))

    # 8. LLM 调用（真实调一次 DeepSeek）
    def _llm():
        from src.llm.gateway import LLMGateway
        llm = LLMGateway().build_llm()
        return llm.complete("用一句话回复：连通测试")
    results.append(check("DeepSeek API", _llm))

    passed = sum(1 for x in results if x)
    print("-" * 60)
    print(f"通过 {passed}/{len(results)} 项")
    if passed < len(results):
        print("存在失败项，请先修复后再继续。")
        sys.exit(1)
    print("环境就绪，可以进入 01 步生成数据。")


def _ping_mongo():
    import pymongo
    try:
        c = pymongo.MongoClient(env["MONGO_URI"], serverSelectionTimeoutMS=3000)
        c.admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    main()
