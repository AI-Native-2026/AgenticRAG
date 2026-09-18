# 架构设计

## 分层

```
前端 React 控制台
   │ REST + SSE (JWT)
API 层 (FastAPI, 模块化 routers)
   auth / chat / datasources / jobs / knowledge-bases /
   documents / retrieval / eval / admin
   │
Agent 层
   工具注册中心 + 角色权限 + 审计
   工具: kb_search / kb_search_by_tenant / list_datasources /
         describe_table / sql_query / calculator
   会话持久化 + 多轮记忆 + 引用血缘
   │
检索层
   混合检索(向量 + BM25/jieba, RRF 融合) → CrossEncoder 重排 → 元数据/租户过滤
   Text-to-SQL 只读检索器
   │
缓存 & LLM 网关
   Redis: embedding 缓存 / 检索缓存 / 语义缓存
   网关: 重试退避 + 令牌桶限流 + 熔断 + GPU 单写者锁 + 用量计量 + KV 统计
   │
存储层
   MongoDB: nodes(真相源) / documents / indexes / sessions / audit /
            lineage / metering / tenants / datasources / ingest_jobs /
            table_schemas / db_sync_state / knowledge_bases
   ChromaDB: 向量 (collection: agentic_rag_nodes)
   Redis: 缓存
   ▲
入库流水线
   连接器 → 统一文档模型 → 去重/版本 → 切分 → 批量 Embedding →
   写 docstore/向量库 → 增量水位 → 血缘
   队列: Kafka(doc_ingest / doc_ingest_dlq) + Producer/Consumer 抽象
   ▲
数据接入层（连接器框架）
   文件: md/txt/pdf/docx/pptx/html/csv/xlsx/json
   数据库: MySQL/PostgreSQL/SQLite/SQL Server/Oracle/MongoDB
     同步模式: 表 → 统一文档 → 向量化
     实时模式: Text-to-SQL → 只读查询
   Web: URL 抓取
```

## 连接器抽象

```python
class BaseConnector:
    def test_connection() -> (bool, str)
    def discover() -> list[ResourceMeta]
    def describe(resource) -> SchemaInfo
    def read(resource, watermark, limit) -> Iterator[RawDocument]
    def live_query(question, schema_text) -> dict
```

通过 `@register("mysql")` 装饰器注册，`create_connector(datasource, credentials)` 工厂实例化。
新增数据源只需实现该接口并注册，无需改动流水线与 API。

## 统一文档 / Chunk 模型

```python
chunk = {
  "node_id", "ref_doc_id", "tenant", "text",
  "source_type": "file|database|web",
  "datasource_id",
  "doc_name", "doc_type", "doc_version", "chunk_idx",
  "metadata": {"page","sheet","table","row_id","url","heading", ...}
}
```

标准字段用于过滤/引用，`metadata` 保留源特有信息（扁平化后写入 Chroma）。

## 安全护栏

| 面 | 措施 |
|---|---|
| 认证 | JWT (HS256)，payload 仅身份字段 |
| 租户隔离 | tenant 一律取自 JWT；检索强制 `where.tenant`；数据源访问校验归属 |
| 工具治理 | 注册中心 + 角色白名单 + 全量审计 + 事件 |
| Text-to-SQL | 只读账号 + sqlglot 解析 + 语句/表白名单 + 去注释/拒多语句 + 强制 LIMIT + 超时 + 行数上限 |
| 凭证 | Fernet(AES) 加密存储，缺失时降级 HMAC-XOR（仅开发） |
| 配额 | 日 Token 上限 + 存储节点上限 + 按租户令牌桶限流 |
| 注入防御 | 系统提示明确检索内容为不可信输入，忽略其中指令 |

## 关键设计取舍

- **同步 vs 队列**：数据源同步走直连后台任务（长任务、需进度）；单篇文档走 Kafka（削峰、可重放）。
- **向量库**：Chroma 单机持久化，适配器接口预留 Qdrant/Milvus 替换点。
- **事件观测**：JSONL sink，预留 Mongo/Prometheus 替换点。
- **增量同步**：数据库连接器按水位线字段增量；文件按内容 hash 去重。
