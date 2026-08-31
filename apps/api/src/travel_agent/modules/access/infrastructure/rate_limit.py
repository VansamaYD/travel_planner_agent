from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self._attempts = attempts
        self._window_seconds = window_seconds
        self._failures: defaultdict[str, deque[float]] = defaultdict(deque)

    def key(self, client_host: str, login: str) -> str:
        value = f"{client_host}|{login.strip().casefold()}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def allowed(self, key: str) -> bool:
        failures = self._active_failures(key)
        return len(failures) < self._attempts

    def record_failure(self, key: str) -> None:
        failures = self._active_failures(key)
        failures.append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def _active_failures(self, key: str) -> deque[float]:
        failures = self._failures[key]
        threshold = time.monotonic() - self._window_seconds
        while failures and failures[0] < threshold:
            failures.popleft()
        return failures
