"""令牌桶限流（对应 v2 手册 04 篇）。

为什么用令牌桶而不是"每秒计数重置"：
  令牌桶允许"突发 + 平均限速"：桶容量=最大突发量，速率=平均每秒补充的令牌。
  比如容量 10、速率 5/s：可以瞬间连发 10 个，然后按 5/s 补充。
  （每秒重置计数的简单计数器无法支持突发，且边界时刻有 bug。）

应用场景（v2）：
  按租户限流 —— 每个租户一个桶，防止单个租户打爆 LLM API / GPU。
"""

import threading
import time
from typing import Dict


class TokenBucket:
    """线程安全的令牌桶。"""

    def __init__(self, capacity: float, rate: float):
        self.capacity = capacity          # 桶容量 = 最大突发
        self.rate = rate                  # 补充速率（令牌/秒）
        self.tokens = capacity            # 当前令牌
        self.last = time.monotonic()      # 上次补充时间
        self._lock = threading.Lock()

    def try_acquire(self, n: int = 1) -> bool:
        """尝试取 n 个令牌。够则扣并返回 True，不够返回 False（不阻塞）。"""
        with self._lock:
            now = time.monotonic()
            # 先按流逝时间补充令牌（rate * 秒）
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= n:
                self.tokens -= n
                return True
            return False


class TenantRateLimiter:
    """按租户维护令牌桶。没见过的租户自动建桶（默认宽松），避免误伤新租户。"""

    def __init__(self, default_capacity: float = 20, default_rate: float = 10):
        self.default_capacity = default_capacity
        self.default_rate = default_rate
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def allow(self, tenant: str, n: int = 1) -> bool:
        with self._lock:
            bucket = self._buckets.get(tenant)
            if bucket is None:
                bucket = TokenBucket(self.default_capacity, self.default_rate)
                self._buckets[tenant] = bucket
        return bucket.try_acquire(n)

    def set_limit(self, tenant: str, capacity: float, rate: float) -> None:
        """管理端给某租户设定配额（配合 storage/quota）。"""
        with self._lock:
            self._buckets[tenant] = TokenBucket(capacity, rate)


if __name__ == "__main__":
    rl = TenantRateLimiter(default_capacity=3, default_rate=1)
    for i in range(5):
        ok = rl.allow("tech")
        print(f"第{i+1}次: {'放行' if ok else '限流'}")
    time.sleep(1.1)
    print("1秒后再试:", "放行" if rl.allow("tech") else "限流")
