"""Agent 层（对应学习手册 06 篇）。

tools.py : 定义 Agent 可用的工具（kb_search 等）
agent.py : 构建 FunctionAgent（深思考 + 工具调用 + 多轮记忆）

Agent 化 RAG 与普通 RAG 的本质区别：
  普通 RAG：query 进 → 检索一次 → LLM 回答（单轮固定流水线）
  Agentic RAG：LLM 自主决定"要不要查、查几次、查哪个库、查完要不要再查"
     → 能处理多跳问题（如"对比两家公司的功耗，帮我算差额"）
"""
