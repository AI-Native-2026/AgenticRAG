"""熔断器（对应 v2 手册 04 篇）。

问题：LLM API 挂了/限流，如果一直硬请求，会雪崩（连接池占满、超时堆积）。
熔断器思路（断路器模式）：
  连续失败 N 次 → 电路打开(OPEN)：立刻拒绝所有请求（快速失败），让下游喘息
  → 一段时间后进入半开(HALF_OPEN)：放 1 个探测请求
    · 成功 → 关闭(CLOSED)：恢复正常
    · 失败 → 重新打开

状态机：
  CLOSED --失败数>=阈值--> OPEN
  OPEN   --等待时间到-----> HALF_OPEN
  HALF_OPEN --探测成功-->  CLOSED
  HALF_OPEN --探测失败-->  OPEN
"""

import threading
import time
from typing import Optional


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold   # 连续失败多少次打开
        self.recovery_timeout = recovery_timeout     # 打开后等多久半开
        self.state = "CLOSED"
        self.failures = 0
        self.opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def call(self, fn, *args, **kwargs):
        """在熔断保护下执行函数。电路打开时直接抛 CircuitOpenError。"""
        if not self.allow():
            raise CircuitOpenError(f"熔断器已打开（连续 {self.failures} 次失败）")
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:  # noqa: BLE001 —— 熔断器要捕获所有下游异常
            self.record_failure()
            raise

    def allow(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                # 冷却时间到 → 进入半开，放一个探测请求
                if time.time() - self.opened_at >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    return True
                return False
            if self.state == "HALF_OPEN":
                return True  # 只放一个探测（并发下由锁保证同时只有一个）
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.state = "CLOSED"
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state == "HALF_OPEN" or self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self.opened_at = time.time()

    @property
    def is_open(self) -> bool:
        return not self.allow()


class CircuitOpenError(Exception):
    pass


if __name__ == "__main__":
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)

    def flaky():
        raise ValueError("API 挂了")

    for i in range(4):
        try:
            cb.call(flaky)
        except CircuitOpenError as e:
            print(f"第{i+1}次: 熔断快速失败 -> {e}")
        except ValueError:
            print(f"第{i+1}次: 真实调用失败（failures={cb.failures}, state={cb.state}）")
    time.sleep(1.2)
    print("冷却后状态:", cb.state, "| allow:", cb.allow())
