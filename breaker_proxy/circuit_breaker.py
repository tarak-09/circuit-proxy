import asyncio
import time
import logging
from enum import Enum
from typing import collections
from .metrics import CIRCUIT_STATE, REQUESTS_TOTAL, FAILURE_RATE

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(
        self,
        url: str = "default",
        failure_threshold_ratio: float = 0.5,
        min_requests: int = 5,
        window_size_seconds: float = 10.0,
        reset_timeout_seconds: float = 5.0,
        half_open_max_probes: int = 3,
    ):
        self.url = url
        self.failure_threshold_ratio = failure_threshold_ratio
        self.min_requests = min_requests
        self.window_size_seconds = window_size_seconds
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_max_probes = half_open_max_probes
        
        self.state = CircuitState.CLOSED
        CIRCUIT_STATE.labels(url=self.url).state(self.state.value)
        
        # Store events as (timestamp, is_failure)
        self.history = collections.deque()
        
        self._half_open_probes = 0
        self._reset_task = None

    def record_success(self):
        REQUESTS_TOTAL.labels(url=self.url, status='success').inc()
        self._record_event(is_failure=False)
        if self.state == CircuitState.HALF_OPEN:
            self._half_open_probes += 1
            if self._half_open_probes >= self.half_open_max_probes:
                logger.warning(f"CircuitBreaker[{self.url}]: Probes successful. Transitioning to CLOSED.")
                self._transition_to_closed()

    def record_failure(self):
        REQUESTS_TOTAL.labels(url=self.url, status='failure').inc()
        self._record_event(is_failure=True)
        if self.state == CircuitState.CLOSED:
            self._check_failure_rate()
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"CircuitBreaker[{self.url}]: Probe failed. Transitioning to OPEN.")
            self._transition_to_open()

    def _record_event(self, is_failure: bool):
        now = time.monotonic()
        self.history.append((now, is_failure))
        self._cleanup_history(now)

    def _cleanup_history(self, now: float):
        # Remove events outside the window
        while self.history and self.history[0][0] < now - self.window_size_seconds:
            self.history.popleft()

    def _update_failure_rate_metric(self):
        total = len(self.history)
        if total == 0:
            FAILURE_RATE.labels(url=self.url).set(0.0)
            return 0.0
        failures = sum(1 for _, is_fail in self.history if is_fail)
        rate = failures / total
        FAILURE_RATE.labels(url=self.url).set(rate)
        return rate

    def _check_failure_rate(self):
        now = time.monotonic()
        self._cleanup_history(now)
        
        total = len(self.history)
        rate = self._update_failure_rate_metric()
        if total < self.min_requests:
            return
            
        if rate >= self.failure_threshold_ratio:
            logger.warning(f"CircuitBreaker[{self.url}]: Failure rate {rate:.2f} exceeded threshold {self.failure_threshold_ratio:.2f}. Transitioning to OPEN.")
            self._transition_to_open()

    def _transition_to_open(self):
        self.state = CircuitState.OPEN
        CIRCUIT_STATE.labels(url=self.url).state(self.state.value)
        self.history.clear()
        self._update_failure_rate_metric()
        
        if self._reset_task:
            self._reset_task.cancel()
        
        self._reset_task = asyncio.create_task(self._reset_timer())

    def _transition_to_closed(self):
        self.state = CircuitState.CLOSED
        CIRCUIT_STATE.labels(url=self.url).state(self.state.value)
        self.history.clear()
        self._update_failure_rate_metric()
        self._half_open_probes = 0
        if self._reset_task:
            self._reset_task.cancel()
            self._reset_task = None

    def manual_reset(self):
        """Manually force the circuit breaker into CLOSED state."""
        logger.info(f"CircuitBreaker[{self.url}]: Manually resetting to CLOSED.")
        self._transition_to_closed()

    def _transition_to_half_open(self):
        logger.warning(f"CircuitBreaker[{self.url}]: Reset timeout elapsed. Transitioning to HALF_OPEN.")
        self.state = CircuitState.HALF_OPEN
        CIRCUIT_STATE.labels(url=self.url).state(self.state.value)
        self._half_open_probes = 0

    async def _reset_timer(self):
        try:
            await asyncio.sleep(self.reset_timeout_seconds)
            self._transition_to_half_open()
        except asyncio.CancelledError:
            pass

    def can_request(self) -> bool:
        """Checks if a request is allowed to pass through the circuit breaker."""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            return False
        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited number of concurrent probes
            if self._half_open_probes < self.half_open_max_probes:
                return True
            return False
        return False
