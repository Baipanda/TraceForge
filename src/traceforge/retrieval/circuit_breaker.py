"""Three-state circuit breaker shared by embed path and tool-level calls."""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """CLOSED → OPEN (after N failures) → HALF_OPEN (after cooldown) → CLOSED."""

    def __init__(self, failure_threshold: int = 5, recovery_s: float = 60.0, *, name: str = "") -> None:
        self.threshold = max(1, failure_threshold)
        self.recovery_s = max(0.1, recovery_s)
        self.name = name or "breaker"
        self.state = CircuitState.CLOSED
        self.fail_count = 0
        self.opened_at: Optional[float] = None

    def allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.opened_at is not None and time.monotonic() - self.opened_at >= self.recovery_s:
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit half-open name=%s", self.name)
                return True
            return False
        return True  # HALF_OPEN: allow one probe

    def record_success(self) -> None:
        self.fail_count = 0
        self.state = CircuitState.CLOSED
        self.opened_at = None

    def record_failure(self) -> None:
        self.fail_count += 1
        if self.fail_count >= self.threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            logger.warning(
                "circuit open name=%s consecutive_fails=%s recovery_s=%.0f",
                self.name,
                self.fail_count,
                self.recovery_s,
            )

    def snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "fail_count": self.fail_count,
            "threshold": self.threshold,
            "recovery_s": self.recovery_s,
            "opened_at": self.opened_at,
        }
