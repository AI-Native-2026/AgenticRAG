# Agentic RAG 知识中台

企业级知识中台：统一接入**多格式文件**与**多种数据库**，提供混合检索、重排、
Agent 编排、工具治理与全链路观测，并配有 React 控制台。

## 架构

```
React 控制台 (Vite + TS)
      │ REST + SSE (JWT)
FastAPI 服务层（routers: auth/chat/datasources/jobs/kb/documents/retrieval/admin）
      │
Agent 层：工具注册中心 + 权限 + 审计
  kb_search | sql_query | list_datasources | describe_table | calculator
      │
检索层：混合检索(向量+BM25+RRF) → CrossEncoder 重排 → 元数据/租户过滤
      │
缓存层：Redis（embedding/检索/语义缓存）
LLM 网关：重试 + 限流 + 熔断 + GPU 锁 + 用量计量
      │
存储层：MongoDB（真相源/索引/会话/审计/血缘/计量/租户/数据源/任务）
        + ChromaDB（向量）
      ▲
入库流水线：连接器框架 → 解析 → 统一文档模型 → 切分 → 去重 → 批量 Embedding
            → 版本化写库 → 增量水位 → 血缘
      ▲
数据接入层（连接器）
  文件：md/txt/pdf/docx/pptx/html/csv/xlsx/json
  数据库：MySQL/PostgreSQL/SQLite/SQL Server/Oracle/MongoDB
    ├─ 同步模式：表/视图 → 统一文档 → 向量化
    └─ 实时模式：Text-to-SQL → 只读查询
  Web：URL 抓取
```

## 目录

```
backend/    Python 后端（FastAPI + LlamaIndex + Chroma + Mongo + Redis + Kafka）
frontend/   React + TS + Vite 控制台（prototype/ 为纯 HTML 高保真原型）
deploy/     部署脚本
docs/       设计文档
```

## 快速开始

### 后端

```bash
cd backend
cp .env.example .env          # 填入 DEEPSEEK_API_KEY 等
pip install -r requirements.txt

# 前置：MongoDB / Redis 已启动；本地可用 QUEUE_BACKEND=dev 免 Kafka
python scripts/run_api.py
```

### 前端

```bash
cd frontend
npm install
npm run dev                   # 默认 http://localhost:5173，代理到 :8000
```

演示账号：`admin / admin123`（租户 tech，管理员）

## 数据接入

- **文件**：新建数据源 `type=file, subtype=directory`，config.path 指向目录
- **数据库**：新建数据源 `type=database, subtype=mysql|postgresql|...`，
  填写 host/port/database 与只读账号密码；支持连接测试、Schema 浏览、
  全量/增量同步、Text-to-SQL 实时查询
- **Web**：`type=web`，config.url 为起始地址

## 安全护栏

- JWT 鉴权；tenant 一律取自 token，不信任请求体
- 工具调用按角色鉴权 + 全量审计
- Text-to-SQL：只读账号 + 语句白名单 + 表白名单 + 强制 LIMIT + 超时
- 数据源凭证加密存储（cryptography.Fernet，缺失时降级 HMAC-XOR）
