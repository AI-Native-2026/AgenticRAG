"""Agentic RAG 教学示例 源码包。

目录结构：
  src/config.py     全局配置（读取 test.env + 路径铁律）
  src/llm/          LLM 网关（DeepSeek + 重试/退避 + embedding 初始化）
  src/ingestion/    离线流水线（加载/切分/去重/写库）
  src/storage/      存储层（Mongo docstore + Mongo index_store + Chroma + Redis）
  src/retrieval/    检索层（BM25 / 混合检索 / 重排 / 过滤）
  src/agent/        Agent 层（工具 + FunctionAgent + 会话持久化）
"""
