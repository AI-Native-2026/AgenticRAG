"""令牌桶限流测试。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.rate_limit import TenantRateLimiter, TokenBucket  # noqa: E402


def test_token_bucket_burst_then_limited():
    """容量 3：前 3 次放行，第 4 次拒绝（突发用尽）。"""
    bucket = TokenBucket(capacity=3, rate=0.1)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()  # 桶空


def test_token_bucket_refills_over_time():
    """速率 1/s：等 1.1 秒后恢复 1 个令牌。"""
    bucket = TokenBucket(capacity=2, rate=1.0)
    bucket.try_acquire()
    bucket.try_acquire()
    assert not bucket.try_acquire()
    time.sleep(1.1)
    assert bucket.try_acquire()  # 补充回来了


def test_tenant_isolated():
    """租户间互不影响：tech 被打满，finance 照常。"""
    rl = TenantRateLimiter(default_capacity=1, default_rate=0.1)
    assert rl.allow("tech")
    assert not rl.allow("tech")
    assert rl.allow("finance")  # 独立桶
