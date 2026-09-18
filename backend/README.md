# 后端（Agentic RAG 知识中台）

FastAPI + LlamaIndex + ChromaDB + MongoDB + Redis + Kafka。

## 结构

```
src/
  config.py              统一配置（env > .env > 默认）
  connectors/            数据接入层：file / sql / mongo / web + text2sql
  ingestion/             流水线：chunker / dedup / pipeline / sync / producer / consumer
  storage/               docstore / vector / cache / audit / lineage / metering /
                         quota / datasource / job / kb / schema / sync_state / crypto
  retrieval/             bm25 / hybrid(RRF) / rerank / filters
  agent/                 tools(含 sql_query) / registry / agent / session
  api/                   main + services + deps + schemas + routers/
  observability/         events / sink / metrics / alerts / logger
  llm/                   gateway(重试/限流/熔断/GPU锁/计量) / rate_limit / circuit_breaker
scripts/                 00_check_env ~ 05_eval + run_api + run_consumer + admin/
tests/                   pytest
```

## 运行

```bash
cp .env.example .env        # 填 DEEPSEEK_API_KEY 等
pip install -r requirements.txt
python scripts/run_api.py           # API :8000
python scripts/run_consumer.py      # Kafka 消费者（QUEUE_BACKEND=kafka 时）
```

本地无 Kafka 时设 `QUEUE_BACKEND=dev` 使用内存队列。

## 部署

```bash
bash ../deploy/install.sh
bash ../deploy/start_all.sh start     # 起 Mongo/Redis/Kafka + API + Consumer
bash ../deploy/start_all.sh status
```

前端 `npm run build` 后，后端会自动挂载 `frontend/dist` 实现单端口访问。
