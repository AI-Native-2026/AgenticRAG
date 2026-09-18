# v2 04 LLM 网关增强

> 本节回答：LLM 调用在生产上为什么会崩、限流/熔断/GPU 锁各解决什么问题。

## 4.1 v1 网关只有"重试"，够吗？

v1 的 `chat()` 失败就指数退避重试。但重试解决不了三件事：
1. **单个租户打爆 QPS**：重试只会让雪崩更严重
2. **LLM 持续不可用**：一直重试 = 一直白白超时堆积
3. **并发抢 GPU**：多个请求同时 embedding/重排，显存溢出

v2 网关 = 重试（保留）+ 限流 + 熔断 + GPU 单写者锁 + KV 统计，五层防护。

## 4.2 令牌桶限流（`llm/rate_limit.py`）

```python
class TokenBucket:
    def try_acquire(self, n=1):
        # 先按流逝时间补充令牌：tokens = min(capacity, tokens + Δt * rate)
        # 够则扣，不够返回 False
```

**为什么令牌桶而不是"每秒计数重置"**：
- 每秒重置：到点瞬间清零，边界时刻容易误放/误拒，且不支持突发
- 令牌桶：容量=最大突发（可瞬间连发 N 个），速率=平均补充（之后按 5/s 补）
  两个参数分别控制"突发上限"和"平均上限"

**按租户隔离**：`TenantRateLimiter` 每个租户一个桶，`tech` 被打满不影响
`finance`——防"一个租户拖垮全体"。

## 4.3 熔断器（`llm/circuit_breaker.py`）

```
CLOSED --连续失败≥阈值--> OPEN --冷却时间到--> HALF_OPEN
HALF_OPEN --探测成功--> CLOSED
HALF_OPEN --探测失败--> OPEN
```

```python
def allow(self):
    if self.state == "OPEN" and time.time() - self.opened_at >= self.recovery_timeout:
        self.state = "HALF_OPEN"   # 放一个探测请求
        return True
    return self.state != "OPEN"
```

**为什么需要熔断而不是无限重试**：
LLM API 挂掉时，如果每个请求都重试 3 次还超时，所有请求都堆在超时等待里，
连接池占满 → 雪崩。熔断在连续失败后**快速失败**（立刻抛错不等待），
让 API 有时间恢复；冷却后放一个探测请求试水，成功了再恢复流量。

**为什么半开只放一个**：并发场景下如果半开放很多个，API 其实还没好，
又立刻全失败 → 又一次雪崩。一次只试一个，是最小代价的探测。

## 4.4 GPU 单写者锁（`gateway.py`）

```python
MODEL_LOCK = threading.RLock()   # 全局锁

class ModelExecutor:
    @staticmethod
    def embed(embed_model, texts):
        with MODEL_LOCK:
            return embed_model.get_text_embedding_batch(texts)
```

**为什么必须串行 GPU 推理**：
单块 GPU 显存有限。API 多个请求 + 队列消费者同时调 embedding/重排模型，
并发执行会显存 OOM 崩溃。全局锁保证**同时只有一个线程在推理**——
代价是等锁（毫秒级），换来的是稳定。

**为什么用 RLock（可重入）**：检索链路可能嵌套调用（retriever 内嵌模型调用），
RLock 允许同一线程重入，避免自己锁死自己。

## 4.5 KV/Prompt 前缀缓存（诚实边界）

**先说清楚**：真正的 KV 缓存是**服务商侧**的自动特性（DeepSeek/OpenAI 对
"命中缓存的 prompt 前缀"收费大降），应用层**无法直接控制**它。

应用层能做的两件事（v2 落地）：
1. **prompt 组织成可缓存形状**：系统提示 + 稳定上下文固定放最前、顺序不变
   （前缀缓存的命中条件 = 前缀逐字节一致）
2. **统计命中情况**：从响应 usage 里读 `cached_tokens`，算出命中率，
   进成本报表——"我们到底省了多少"

```python
def _record_kv_stats(self, resp):
    prompt_tokens = usage.get("prompt_tokens", 0)
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
    self.kv_stats["cached_tokens"] += cached
```

**为什么不把它当"我们的缓存"**：KV 缓存不归应用管，写代码时如果不标注
边界，学生容易误以为"我们实现了 KV 缓存"。诚实标注 = 教学价值。

## 4.6 运行与验证

```bash
python src/llm/rate_limit.py          # 令牌桶行为演示
python src/llm/circuit_breaker.py     # 熔断状态机演示
python -m pytest tests/ -v            # 测试覆盖：限流/熔断
```

预期：
```
test_token_bucket_burst_then_limited ... passed
test_token_bucket_refills_over_time  ... passed
test_tenant_isolated                 ... passed
test_opens_after_threshold_failures  ... passed
test_recovers_to_closed_on_success   ... passed
```

## 4.7 思考题

❓ 问题：令牌桶容量和速率分别调大调小，会发生什么？QPS 上限到底是哪个参数决定的？
💡 为什么这么问：两个参数容易混，实际是"突发上限 vs 平均上限"两个维度。
🔍 参考思路：容量=瞬时突发，速率=稳态；QPS 上限由速率决定（1/rate 秒一个），
   容量决定"能突发放多少个"。容量远大于速率时才有意义。

❓ 问题：熔断器恢复时间设成 1 秒和 60 秒，各自风险是什么？
💡 为什么这么问：恢复太快探得勤（API 没好会反复雪崩），太慢会长时间拒绝可用请求。
🔍 参考思路：1 秒 → API 恢复前每 1 秒就试一次，没恢复就又是一次失败波动；
   60 秒 → API 其实 5 秒就好了，但 55 秒内所有请求都被拒。生产中配合
   实际 API 的恢复特性调。

❓ 问题：为什么 GPU 推理要全局串行？多卡场景下这个锁还成立吗？
💡 为什么这么问：单写者锁是"单卡"的解法，要理解它什么时候失效。
🔍 参考思路：多卡时按卡分锁（每张卡一把锁）即可并行；全局锁只是教学
   单机的简化。真正的生产答案是"模型服务化"（独立推理服务 + 队列），
   彻底摆脱进程内共享。

> 下一步：[05 安全与多租户](05_安全与多租户.md)
