# v2 01 API 服务化

> 本节回答：怎么把命令行系统变成"别人能调的 HTTP 服务"，每一步为什么。

## 1.1 为什么要做 API 层

v1 的系统只能命令行用。生产上要接前端/其他服务，必须：
- **标准接口**：HTTP + JSON，任何语言都能调
- **鉴权**：谁在调、凭什么调
- **流式**：长回答不阻塞，用户能看到"正在生成"
- **可运维**：健康检查让负载均衡知道"哪台活着"

## 1.2 为什么用 FastAPI（vs Flask）

| 能力 | Flask | FastAPI |
|---|---|---|
| 自动校验请求 | 手写 | **Pydantic 模型自动校验**，错了返回 422 |
| 自动文档 | 无 | OpenAPI 文档自动生成（/docs 直接看） |
| 异步 | 需自己跑线程池 | **原生 async**，SSE/长连接天然友好 |

FastAPI 的"异步 + 类型校验 + 自动文档"正好是 API 服务三件套，选它零多余。

## 1.3 核心代码讲解：`src/api/main.py`

### 1.3.1 统一错误响应

```python
class AppError(Exception):
    def __init__(self, status_code, code, message):
        ...

@app.exception_handler(AppError)
async def app_error_handler(request, exc):
    return Response(
        content=json.dumps({"code": exc.code, "message": exc.message}, ensure_ascii=False),
        status_code=exc.status_code, media_type="application/json")
```

**为什么统一 `{code, message}`**：前端/CLI 判断逻辑只认 `code`，不解析人类文案。
比如 `UNAUTHORIZED`、`QUOTA_EXCEEDED`、`RATE_LIMITED`，程序 switch 一下就知道怎么办。

### 1.3.2 AppServices：重量级组件只建一次

```python
class AppServices:
    def __init__(self):
        self.embed_model = build_embed_model()   # GPU 模型（几百 MB）
        self.hybrid = HybridRetriever(...)        # BM25 索引
        self.reranker = Reranker(...)             # 重排模型
        ...
```

**为什么用 `app.state.svc` 单例**：
embedding 模型、重排模型加载一次要几十秒、占几 GB 内存。如果每个请求
都新建，服务直接崩。启动时建一次，请求间**共享**——这就是"重量级组件
单例化"的生产常识。

### 1.3.3 健康检查：healthz vs readyz

```python
@app.get("/healthz")   # 存活：进程活着就 200
@app.get("/readyz")    # 就绪：Mongo/Redis/Kafka 全可用才 200
```

**为什么要有两个**：
- `healthz`：进程没崩就行（k8s livenessProbe 用）
- `readyz`：依赖全就绪才行，一个依赖挂就返回 503（k8s readinessProbe 用，
  让负载均衡把不健康的实例摘出去，不把请求打进"半死"的服务）

### 1.3.4 文档提交 + 幂等键

```python
if body.idempotency_key:
    key = f"idem:{body.idempotency_key}"
    if not svc.cache.redis.set(key, "1", nx=True, ex=3600):
        return DocSubmitResponse(accepted=len(body.docs), request_id="duplicate-skip")
```

**为什么需要幂等键**：
客户端提交文档时，如果网络抖动导致重试，同一批文档会被**入队两次**。
用 `SET key NX`（不存在才写入）：第一次成功写 key，第二次发现 key 存在
直接返回"已提交"——**重试不产生重复**。这是所有"提交型接口"的标准做法。

### 1.3.5 SSE：传输层方案（v2 的核心决策）

```python
@app.post("/v1/chat")
async def chat(request, body):
    ...
    result = await svc.rag.achat(...)      # 内部非流式，一次拿到完整答案
    events = [("start", {...}), ("answer", {...}), ("done", {...})]
    async def gen():
        for event, data in events:
            yield sse_event(event, data)
    return StreamingResponse(gen(), media_type="text/event-stream")
```

**为什么是"SSE 只做传输层"**：
- v1 实测 `openai_like + 工具 + 流式` 组合会触发底层 bug（`completions` 端点
  不接受 `tools` 参数），token 级流式暂时不可用
- 但**体验上**用户仍需要"看到事件流"（start → answer → done）
- 方案：生成走非流式（稳定），SSE 负责把"进度/结果/结束"分帧推给客户端
- token 级流式留作 v2 后续（依赖升级后补），**先保证稳定再谈体验**

## 1.4 运行与验证

```bash
python scripts/run_api.py            # 前台
bash scripts/start_services.sh start # 或随服务一起启动

# 冒烟测试一键验证
python scripts/smoke_api.py
```

预期（8/8 通过）：

```
[OK] 登录: token=eyJhbGciOiJIUzI1NiIs...
[OK] healthz / readyz
[OK] 提交文档(队列) / 幂等键
[OK] Agent 对话(SSE): 回答(...字)
[OK] 指标报表 / 会话历史
通过 8/8 项
```

## 1.5 踩坑记录

| 现象 | 根因 | 修复 |
|---|---|---|
| `/v1/chat` 返回 500，日志 `asyncio.run() cannot be called from a running event loop` | `AgenticRAG.chat()` 用 `asyncio.run()`，但 FastAPI 端点**已经跑在事件循环里**，不能再开一个 | 加 `achat()` 异步方法，端点里 `await` 直接调用 |
| 未带 token 调用接口 | 无鉴权 | `_get_bearer()` 统一从 header 解析 JWT，无效即 401 |

## 1.6 思考题

❓ 问题：healthz 和 readyz 都返回 200 时，服务一定健康吗？readyz 里哪些依赖可以允许暂时不可用？
💡 为什么这么问：健康检查不是"越严格越好"，过度严格会导致负载均衡把所有实例都摘掉（全黄）。
🔍 参考思路：readyz 应检查**该实例提供服务所必需**的依赖；缓存类可降级组件可以容忍短暂不可用；
   错误方向是"一个无关依赖挂了整个实例被摘"，反而放大故障。

❓ 问题：为什么"重量级组件单例化"能撑住并发，而"每请求新建"会崩？
💡 为什么这么问：理解"启动成本 vs 请求成本"的边界。
🔍 参考思路：模型加载是几十秒的 I/O + 计算，请求是毫秒级调用；共享只读对象 + 线程锁（GPU 单写者）
   让并发请求复用同一份模型，代价只是等锁而不是重新加载。

❓ 问题：幂等键如果 1 小时内被用同一个 key 提交了两批**不同**的文档，会怎样？
💡 为什么这么问：幂等键的正确语义是"同一个业务操作"，不是"同一个 key"。
🔍 参考思路：客户端应为每个业务提交生成唯一 key；如果复用 key 提交不同内容，服务端会误判为重复而丢弃第二批——这是"幂等键的滥用"。

> 下一步：[02 可观测性](02_可观测性.md)
