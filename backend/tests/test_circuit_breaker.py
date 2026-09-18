"""熔断器测试。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.circuit_breaker import CircuitBreaker, CircuitOpenError  # noqa: E402


def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    for _ in range(3):
        try:
            cb.call(lambda: (_ for _ in ()).throw(ValueError("boom")))
        except ValueError:
            pass
    # 阈值达到 → 打开 → 快速失败
    try:
        cb.call(lambda: "never")
        assert False, "应该抛 CircuitOpenError"
    except CircuitOpenError:
        pass


def test_recovers_to_closed_on_success():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.3)
    for _ in range(2):
        try:
            cb.call(lambda: (_ for _ in ()).throw(ValueError("boom")))
        except ValueError:
            pass
    time.sleep(0.4)  # 冷却结束 → 半开
    assert cb.allow() is True
    cb.record_success()  # 半开探测成功 → 关闭
    assert cb.state == "CLOSED"


def test_success_path_no_interference():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    assert cb.call(lambda: 42) == 42
    assert cb.state == "CLOSED"
    assert cb.failures == 0
