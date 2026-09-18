"""轻量自研可观测性（对应 v2 手册 02 篇）。

为什么自研而不是接 Langfuse：
  自研只需要「一个事件 schema + 一个落盘 + 一个聚合脚本」，零新增组件、
  逻辑全透明（适合教学）；Langfuse 自托管需要 Docker + 额外维护，
  在资源有限的单机上不划算。生产量大后再换也不难——把 Sink 换成
  Langfuse 客户端即可，事件模型不变。

四件套：
  events.py   事件模型（一次请求里每个环节发一条事件，用 request_id 串联）
  logger.py   结构化 JSON 日志（机器可读，便于 grep/聚合/报警）
  sink.py     事件落盘（JSONL 文件 / 可选 Mongo）
  metrics.py  指标聚合（p95 延迟、缓存命中率、每租户 token）
  alerts.py   告警规则引擎（规则文件 + 检查触发）
"""
