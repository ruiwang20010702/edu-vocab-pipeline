"""熔断器状态变化日志测试."""

import logging
import time

from vocab_qc.core.circuit_breaker import CircuitBreaker


class TestCircuitBreakerLogging:

    def test_closed_to_open_logs_warning(self, caplog):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
        with caplog.at_level(logging.WARNING, logger="vocab_qc.core.circuit_breaker"):
            for i in range(3):
                cb.record_failure(f"error-{i}")

        # 达到阈值时应记录一条 WARNING
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "CLOSED → OPEN" in warnings[0].message
        assert "连续失败3次" in warnings[0].message

    def test_half_open_to_open_logs_warning(self, caplog):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        # 先触发熔断
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitBreaker.OPEN

        # 等待冷却进入 HALF_OPEN
        time.sleep(0.06)
        assert cb.state == CircuitBreaker.HALF_OPEN

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="vocab_qc.core.circuit_breaker"):
            cb.record_failure("retry-failed")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "HALF_OPEN → OPEN" in warnings[0].message
        assert "半开重试失败" in warnings[0].message

    def test_open_to_half_open_logs_info(self, caplog):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure("err1")
        cb.record_failure("err2")

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="vocab_qc.core.circuit_breaker"):
            time.sleep(0.06)
            _ = cb.state  # 触发状态转换

        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(infos) == 1
        assert "OPEN → HALF_OPEN" in infos[0].message
        assert "冷却完成" in infos[0].message

    def test_recovery_logs_info(self, caplog):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure("err1")
        cb.record_failure("err2")
        time.sleep(0.06)
        _ = cb.state  # HALF_OPEN

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="vocab_qc.core.circuit_breaker"):
            cb.record_success()

        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(infos) == 1
        assert "→ CLOSED" in infos[0].message
        assert "恢复" in infos[0].message

    def test_no_log_when_already_closed(self, caplog):
        cb = CircuitBreaker(failure_threshold=5)
        with caplog.at_level(logging.DEBUG, logger="vocab_qc.core.circuit_breaker"):
            cb.record_success()

        # CLOSED → CLOSED 不应产生日志
        assert len(caplog.records) == 0

    def test_below_threshold_no_warning(self, caplog):
        cb = CircuitBreaker(failure_threshold=5)
        with caplog.at_level(logging.WARNING, logger="vocab_qc.core.circuit_breaker"):
            cb.record_failure("err1")
            cb.record_failure("err2")

        # 未达阈值不应有 WARNING
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 0

    def test_error_message_in_log(self, caplog):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        with caplog.at_level(logging.WARNING, logger="vocab_qc.core.circuit_breaker"):
            cb.record_failure("connection timeout to ai-gateway")

        assert "connection timeout to ai-gateway" in caplog.records[0].message
