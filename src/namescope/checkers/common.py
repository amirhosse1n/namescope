from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from ..models import CheckResult, CheckStatus, Platform
from ..rules import validate_username


class BaseChecker:
    platform: Platform

    def invalid_result(self, username: str) -> CheckResult | None:
        validation = validate_username(self.platform, username)
        if validation.valid:
            return None
        return CheckResult(
            platform=self.platform,
            username=username,
            status=CheckStatus.INVALID,
            detail=validation.reason,
            checked_at=datetime.now(UTC).isoformat(),
        )

    def result(
        self,
        username: str,
        status: CheckStatus,
        detail: str,
        started: float,
        http_status: int | None = None,
    ) -> CheckResult:
        return CheckResult(
            platform=self.platform,
            username=username,
            status=status,
            detail=detail,
            http_status=http_status,
            latency_ms=round((perf_counter() - started) * 1000),
            checked_at=datetime.now(UTC).isoformat(),
        )

    async def aclose(self) -> None:
        return None
