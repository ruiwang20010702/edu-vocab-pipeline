"""熔断器单元测试."""

import time
from unittest.mock import patch

from vocab_qc.core.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)

        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_default_parameters(self):
        cb = CircuitBreaker()
        assert cb._failure_threshold == 5
        assert cb._recovery_timeout == 30.0

    def test_custom_parameters(self):
        cb = CircuitBreaker(failure_threshold=10, recovery_timeout=60.0)
        assert cb._failure_threshold == 10
        assert cb._recovery_timeout == 60.0

    def test_half_open_failure_reopens_high_threshold(self):
        """F3: HALF_OPEN 下即使 failure_count 远低于阈值，也应立即回到 OPEN。"""
        cb = CircuitBreaker(failure_threshold=15, recovery_timeout=0.1)
        # 先触发熔断
        for _ in range(15):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        # 冷却后进入 HALF_OPEN
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

        # record_success 重置 failure_count → 只需 1 次失败就应回到 OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

        # 再次触发熔断并冷却
        for _ in range(15):
            cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

        # 单次失败立即回到 OPEN（不需累积到 15 次）
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False
