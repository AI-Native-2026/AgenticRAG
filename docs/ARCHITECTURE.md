# 架构设计文档

> Agentic RAG 知识中台 · 版本 3.0

## 1. 目标与定位

面向企业的一体化知识中台：统一接入**多格式文件、多种数据库、Web 与多媒体**，
提供混合检索、统一重排、Agent 编排、工具治理、全链路观测与隐私合规，
并配有 React 控制台。

设计原则：
- **可插拔**：数据源/连接器、重排后端、队列后端、事件 Sink 均可替换
- **可降级**：任何增强能力（OCR/VLM/多模态重排）缺失时自动回退，不阻断主流程
- **多租户隔离**：tenant 贯穿存储、检索、工具、配额
- **隐私合规**：展示层默认脱敏

## 2. 分层架构

```
┌───────────────────────────────────────────────────────────────────┐
│ React 控制台 (Vite + TS + ECharts)                                 │
│ 概览 / 知识库 / 数据源 / 入库任务 / 检索调试 / Agent对话 /           │
│ 评测 / 观测 / 租户配额 / 设置                                       │
└───────────────┬───────────────────────────────────────────────────┘
                │ REST + SSE (JWT)
┌───────────────▼───────────────────────────────────────────────────┐
│ API 层 (FastAPI, 模块化 routers + DI)                              │
│ auth | chat | datasources | jobs | knowledge-bases | documents |   │
│ retrieval | eval | admin | health                                  │
└───────────────┬───────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────┐
│ Agent 层                                                           │
│ 工具注册中心 + 角色权限 + 审计                                      │
│ kb_search / list_datasources / describe_table / sql_query /         │
│ calculator                                                          │
│ 会话持久化 + 上下文管理(短期裁剪 + 长期摘要压缩) + 流式步骤事件      │
└───────────────┬───────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────┐
│ 检索层                                                             │
│ 混合召回(向量 + BM25/jieba, RRF) → 统一重排(CrossEncoder/多模态VL)  │
│ → where 过滤(tenant / datasource / kb)  ← 向量与 BM25 均过滤        │
│ Text-to-SQL 只读检索器(白名单/限流/LIMIT)                           │
└───────────────┬───────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────┐
│ 缓存 & LLM 网关                                                    │
│ Redis: embedding / 检索 / 语义缓存                                 │
│ 网关: 重试退避 + 令牌桶限流 + 熔断 + GPU 单写者锁 + 用量计量 + KV 统计│
└───────────────┬───────────────────────────────────────────────────┘
                │
┌───────────────▼───────────────────────────────────────────────────┐
│ 存储层 (共享 Mongo 连接池)                                         │
│ MongoDB: nodes / documents / indexes / sessions / session_summaries│
│   / audit / lineage / metering / tenants / datasources /           │
│   ingest_jobs / table_schemas / db_sync_state / knowledge_bases     │
│ ChromaDB: 向量 (collection agentic_rag_nodes, cosine HNSW)          │
│ Redis: 缓存                                                         │
└───────────────▲───────────────────────────────────────────────────┘
                │
┌───────────────┴───────────────────────────────────────────────────┐
│ 入库流水线                                                          │
│ 连接器 → 统一文档模型 → 去重/版本 → 切分 → 批量 Embedding(缓存) →    │
│ 写 docstore/向量库 → 增量水位 → 血缘                                │
│ 队列: Kafka(doc_ingest / doc_ingest_dlq) + Producer/Consumer 抽象    │
└───────────────▲───────────────────────────────────────────────────┘
                │
┌───────────────┴───────────────────────────────────────────────────┐
│ 数据接入层（连接器框架）                                            │
│ 文件: md/txt/html/csv/tsv/xlsx/xls/json/pdf/docx/pptx/             │
│       png/jpg/jpeg/bmp/webp/tif (OCR)                              │
│ 数据库: MySQL/PostgreSQL/SQLite/SQL Server/Oracle/MongoDB          │
│   ├ 同步模式: 表/集合 → 统一文档 → 向量化（增量水位线）             │
│   └ 实时模式: Text-to-SQL → 只读查询                               │
│ Web: URL 抓取                                                      │
└───────────────────────────────────────────────────────────────────┘
```

## 3. 连接器框架

统一抽象（`src/connectors/base.py`）：

```python
class BaseConnector:
    def test_connection() -> (bool, str)
    def discover() -> list[ResourceMeta]
    def describe(resource) -> SchemaInfo
    def read(resource, watermark, limit) -> Iterator[RawDocument]
    def preview(resource, limit, max_chars) -> list[RawDocument]   # 轻量预览
    def live_query(question, schema_text) -> dict                  # Text-to-SQL
```

- 通过 `@register("mysql")` 注册，`create_connector(ds, creds)` 工厂实例化
- 新增数据源只需实现接口并注册，无需改动流水线与 API

内置连接器：

| 子类型 | 能力 | 说明 |
|---|---|---|
| file/directory | discover/read/describe/preview | 多格式，目录递归 |
| mysql/postgresql/sqlite/mssql/oracle | +live_query | SQLAlchemy 通用 |
| mongodb | discover/read/describe/preview | 集合与文档 |
| web/url | discover/read | 同域 BFS 抓取 |

### 3.1 富文档与多媒体（`src/connectors/media.py`）

| 类型 | 处理 |
|---|---|
| 图片 | tesseract OCR（chi_sim+eng）；可选 Qwen2.5-VL 描述 |
| PDF | PyMuPDF 按页正文 + `find_tables` 表格转 Markdown；可选整页 OCR |
| docx | python-docx 段落 + 表格转 Markdown |
| pptx | python-pptx 逐页文本框 + 表格 |
| csv/xlsx | 逐行序列化，`modality=table` |

均带优雅降级（unstructured → llama-index → 元数据占位）。

## 4. 统一文档 / Chunk 模型

```python
chunk = {
  "node_id", "ref_doc_id", "tenant", "text",
  "source_type": "file|database|web",
  "datasource_id",
  "doc_name", "doc_type", "doc_version", "chunk_idx",
  "metadata": { "page", "sheet", "table", "row_id", "url",
                "heading", "modality": "text|table|document|image",
                "media_path", "size", "has_table", ... }
}
```

标准字段用于过滤/引用，`metadata` 保留源特有信息（扁平化写入 Chroma）。

## 5. 检索与重排

- **混合召回**：向量（Chroma, cosine）与 BM25（jieba 分词）**并行**执行，RRF 融合
- **强制过滤**：`where`（tenant / datasource_id / kb 并集）同时作用于**向量与 BM25**，
  杜绝跨租户泄漏；BM25 命中携带归一化 metadata
- **统一重排**（`src/retrieval/rerank.py`）：`cross_encoder`（bge-reranker-base，默认）|
  `vl`（Qwen3-VL-Reranker-2B，多模态）| `llm` | `auto`（vl→cross_encoder→llm 逐级降级）
- **Text-to-SQL 护栏**：只读账号 + sqlglot 解析 + 语句/表白名单 + 去注释/拒多语句 +
  强制 LIMIT + 超时 + 行数上限

### 5.1 多模态检索

统一 Embedder（`src/llm/multimodal.py`）：

| `EMBED_BACKEND` | 模型 | 能力 |
|---|---|---|
| `text`（默认） | bge-small-zh-v1.5 | 文本向量；图片走 OCR 文本 |
| `vl` | Qwen3-VL-Embedding-8B（bf16） | 文本与图片映射到**同一向量空间** |

- 入库时按节点类型 embedding：`modality=image` 的节点用图片本体，其余用文本
- 查询侧同样经 Embedder，因此支持**以文搜图**与**以图搜图**
- 向量元数据携带 `modality` / `media_path`，结果与对话引用可显示图片缩略图
- 切换后端时需更换 `CHROMA_COLLECTION` 并重新同步（向量维度不同）

以图搜图接口：`POST /v1/retrieval/search-by-image`（上传图片 → 视觉相似检索）；
媒体访问：`GET /v1/media/{node_id}`（校验租户归属）。

### 5.2 图片理解（VQA）

- `POST /v1/chat/image`：上传图片 + 问题 → 优先用 **Qwen2.5-VL-3B** 视觉模型直接理解图片作答；
  失败/未启用时回退「OCR + 以图检索 + 文本 LLM」。
- 模型惰性加载并缓存（`src/llm/vision.py`），`VLM_DEVICE=auto|cuda|cpu` 控制设备；
  `auto` 会在显存允许时用 GPU，否则 CPU/offload。
- 对话交互：附图**并提问** → 直接作答；**仅附图** → 询问「以图搜图 / 检索相似内容」。

## 6. Agent 层

工具（注册中心 + 角色白名单 + 审计）：

| 工具 | 说明 |
|---|---|
| `kb_search` | 混合检索 + 重排，按租户/知识库范围过滤 |
| `list_datasources` | 列出当前租户数据源 |
| `describe_table` | 查看表结构（Text-to-SQL 前置） |
| `sql_query` | 自然语言实时查询数据库（只读） |
| `calculator` | 安全四则运算 |

上下文管理（`src/agent/memory.py`）：
- **短期记忆**：最近 N 轮原文，token 预算 10K，超预算从最旧裁剪
- **长期记忆**：超窗历史由 LLM 压缩为摘要，持久化到 `session_summaries`，下轮回注
- **会话标题**：首问由 LLM 生成 ≤12 字标题

流式输出：SSE 事件 `start → retrieval/rerank/tool_call/sql → token* → done`；
请求上下文用 `contextvars` 传递（可跨 asyncio 工作线程）。

图表：当用户要图表时，Agent 输出 ` ```echarts ` 代码块，前端用 ECharts 渲染，
并随亮/暗主题自适应。

## 7. 安全与合规

| 面 | 措施 |
|---|---|
| 认证 | JWT (HS256)，payload 仅身份字段 |
| 租户隔离 | tenant 取自 JWT；检索向量+BM25 均过滤；数据源/任务/知识库访问校验归属 |
| 工具治理 | 注册中心 + 角色白名单 + 全量审计 + 事件 |
| Text-to-SQL | 只读 + 解析校验 + 白名单 + LIMIT + 超时 |
| 凭证 | Fernet(AES) 加密存储，缺失时降级 HMAC-XOR |
| 配额 | 日 Token + 存储节点上限 + 按租户令牌桶限流 |
| 隐私 | 预览/文档接口默认 PII 脱敏（手机/邮箱/身份证/银行卡/IP/护照 + 列名感知 name/address），自定义正则 |
| 注入防御 | 系统提示声明检索内容为不可信输入 |

## 8. 性能优化（架构级）

- **共享 Mongo 连接池**：所有 Store 共用一个 `MongoClient`（单例）
- **批量写入**：docstore `bulk_write` 替代逐条 upsert
- **BM25 惰性重建**：`mark_dirty`/`ensure_fresh`，避免批量入库重建风暴
- **并行召回**：向量与 BM25 线程池并行
- **生产者复用**：Kafka Producer 进程级共享
- **Chunker 复用**：SentenceSplitter 实例复用
- **缓存**：embedding / 检索 / 语义三级缓存
- **索引**：node_id(唯一)/ref_doc_id+version/tenant/datasource_id
- **预览**：只读文件头 + 分页 + 字符上限

## 9. 评测

- 评测集支持增删，范围可选：租户 / 知识库 / 数据源
- 指标：Hit Rate、MRR；支持保存基线
- `scripts/05_eval.py` 支持 LLM 裁判与回归门禁

## 10. 测试

| 脚本 | 内容 |
|---|---|
| `scripts/06_multiformat_test.py` | 全格式入库 → 检索（md/txt/html/csv/xlsx/json/pdf/docx/pptx/png/sqlite） |
| `scripts/07_user_journey_test.py` | 管理员/分析师/合规/脱敏 四条用户旅程 |
| `tests/` (pytest) | 鉴权/工具权限/熔断/限流/队列/连接器/Text-to-SQL 护栏 |

## 11. 部署

- `deploy/install.sh`：依赖安装 + 前端构建
- `deploy/start_all.sh`：一键起 Mongo/Redis/Kafka + API + Consumer
- 前端构建后由后端同端口托管（单端口部署）

### 11.1 显存与多模态

启用 `EMBED_BACKEND=vl`（Qwen3-VL-Embedding-8B，bf16 ≈ 16GB）时：

- 单卡 24G 下 **API 与 Kafka 消费者不能同时加载该模型**（会 OOM）。
  此时使用数据源同步入库（在 API 进程内完成），消费者可另起一卡或暂不启用。
- 切换 embedding 后端会改变向量维度，需更换 `CHROMA_COLLECTION` 并重新同步；
  同时清空 Redis 缓存（`redis-cli flushdb`）与 `documents` 去重表以强制重建。
