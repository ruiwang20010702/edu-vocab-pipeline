"""熔断器：连续 N 次失败后快速失败，冷却 M 秒后半开重试。"""

import threading
import time


class CircuitBreaker:
    """简单熔断器，防止 AI 服务宕机时雪崩。

    状态机：CLOSED → (连续失败达阈值) → OPEN → (冷却超时) → HALF_OPEN → 成功回 CLOSED / 失败回 OPEN
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self._state = self.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = self.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        """是否允许请求通过。"""
        current = self.state
        if current == self.CLOSED:
            return True
        if current == self.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        """记录成功，重置计数。"""
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED

    def record_failure(self) -> None:
        """记录失败，达阈值则熔断。"""
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = self.OPEN
                self._last_failure_time = time.monotonic()
