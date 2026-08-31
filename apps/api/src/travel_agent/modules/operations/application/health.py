from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    status: str
    detail: str | None = None

    @property
    def healthy(self) -> bool:
        return self.status in {"ok", "degraded"}


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    checks: tuple[HealthCheckResult, ...]


class ReadinessCheck(Protocol):
    name: str

    async def run(self) -> HealthCheckResult: ...


class HealthService:
    def __init__(self, checks: tuple[ReadinessCheck, ...]) -> None:
        self._checks = checks

    async def readiness(self) -> ReadinessReport:
        results = tuple([await check.run() for check in self._checks])
        return ReadinessReport(
            ready=all(result.healthy for result in results),
            checks=results,
        )
