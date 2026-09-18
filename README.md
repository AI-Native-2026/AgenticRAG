# Agentic RAG 知识中台

企业级知识中台：统一接入**多格式文件、多种数据库、Web 与多媒体**，提供混合检索、
统一重排、Agent 编排、工具治理、全链路观测与隐私合规，并配有 React 控制台。

![Agent 对话 · 各商品订单数量占比](imgs/agenticrag.png)

> 控制台演示：在 **Agent 对话**中提问「各商品的订单数量占比」，小K 自动调用
> `sql_query` 查询数据库，并输出 **ECharts 饼图**展示结果。

## 核心能力

- **多格式接入**：md/txt/html/csv/xlsx/json/pdf/docx/pptx + 图片(OCR) + Web
- **数据库双模式**：表/集合同步入库（增量水位线）+ Text-to-SQL 只读实时查询
- **混合检索**：向量 + BM25（jieba）并行召回，RRF 融合，强制租户/范围过滤
- **统一重排**：bge-reranker / Qwen3-VL 多模态重排（自动降级）
- **Agent 编排**：知识检索 + 数据库查询 + 计算工具，权限与审计
- **会话记忆**：短期 token 预算裁剪 + 长期 LLM 摘要压缩 + 会话标题
- **图表报表**：Agent 输出 ECharts 图表，随亮/暗主题自适应
- **可观测**：事件 / 指标 / 告警 / 审计 / 时序图表
- **评测**：Hit Rate / MRR，按租户/知识库/数据源限定，支持基线
- **安全合规**：JWT + 多租户隔离 + 配额限流 + 凭证加密 + 预览 PII 脱敏

## 架构

```
React 控制台 ──REST/SSE──> FastAPI ──> Agent(工具/记忆/审计)
                                          │
                  混合检索(向量+BM25+RRF) ──> 重排(CE/VL) ──> 过滤(tenant/范围)
                                          │
         Redis 缓存 + LLM 网关(限流/熔断/GPU锁/计量)
                                          │
   Mongo(真相源/索引/会话/审计/血缘/计量/租户/数据源/任务) + Chroma(向量)
                                          ▲
   入库流水线(连接器→统一模型→切分→去重→批量Embedding→版本化) + Kafka 队列
                                          ▲
   数据接入(文件/数据库/Web)  +  富文档/多媒体(PDF表格/Office/图片OCR)
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 目录结构

```
backend/     FastAPI + LlamaIndex + Chroma + Mongo + Redis + Kafka
  src/
    connectors/   连接器框架(file/sql/mongo/web) + media(富文档/OCR) + masking(PII) + text2sql
    ingestion/    流水线(chunker/dedup/sync/producer/consumer)
    storage/      各类 Store + mongo(共享连接池) + crypto(凭证加密)
    retrieval/    bm25 / hybrid / rerank / filters
    agent/        tools / registry / agent / memory
    api/          main + services + deps + schemas + routers/
    observability/ events / sink / metrics / alerts
    llm/          gateway(限流/熔断/GPU锁/计量) / vision
  scripts/        00~07 脚本 + admin/
  tests/          pytest
frontend/    React + TS + Vite + ECharts
  src/pages, components, store, api, styles
  prototype/ 纯 HTML 高保真原型
deploy/      install.sh / start_all.sh
docs/        架构文档
```

## 快速开始

### 后端

```bash
cd backend
cp .env.example .env          # 填 DEEPSEEK_API_KEY 等
pip install -r requirements.txt

# 前置：MongoDB / Redis 已启动；无 Kafka 时设 QUEUE_BACKEND=dev
python scripts/run_api.py           # API :8000
python scripts/run_consumer.py      # Kafka 消费者（QUEUE_BACKEND=kafka）
```

### 前端

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173（代理到 :8000）
# 或 npm run build 后由后端同端口托管
```

演示账号：

| 账号 | 密码 | 租户 | 角色 |
|---|---|---|---|
| admin | admin123 | tech | 管理员 |
| alice | alice123 | tech | 成员 |
| bob | bob123 | finance | 成员 |

## 数据接入

- **文件**：`type=file, subtype=directory`，`config.path` 指向目录
  （支持 md/txt/html/csv/xlsx/json/pdf/docx/pptx + 图片 OCR）
- **数据库**：`type=database, subtype=mysql|postgresql|sqlite|mongodb|...`，
  填连接信息与只读账号；支持连接测试、Schema 浏览、全量/增量同步、Text-to-SQL
- **Web**：`type=web`，`config.url` 为起始地址

## 测试

```bash
cd backend
python -m pytest tests/ -q                    # 单元测试

# 端到端（需 API 运行中）
python scripts/06_multiformat_test.py         # 全格式入库 → 检索
python scripts/07_user_journey_test.py        # 用户旅程
```

## 部署

```bash
bash deploy/install.sh
bash deploy/start_all.sh start     # 起 Mongo/Redis/Kafka + API + Consumer
bash deploy/start_all.sh status
```

## 安全与合规

- JWT 鉴权；tenant 取自 token，检索向量与 BM25 均过滤
- 工具按角色鉴权 + 全量审计
- Text-to-SQL：只读账号 + 语句/表白名单 + 强制 LIMIT + 超时
- 数据源凭证加密存储
- 预览/文档接口默认 PII 脱敏（手机/邮箱/身份证/银行卡/IP/护照 + 列名感知）
