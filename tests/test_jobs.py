import asyncio
from datetime import UTC, datetime

import pytest

from namescope.jobs import JobManager
from namescope.models import CheckResult, CheckStatus, ScanRequest


class FakeStore:
    def seen_usernames(self, platform: str) -> set[str]:
        return set()


class FakeService:
    def __init__(self) -> None:
        self.store = FakeStore()

    async def check(self, platform: str, username: str, force_refresh: bool = False) -> CheckResult:
        return CheckResult(
            platform=platform,
            username=username,
            status=CheckStatus.POSSIBLY_AVAILABLE,
            detail="candidate",
            checked_at=datetime.now(UTC).isoformat(),
        )


def scan_request() -> ScanRequest:
    return ScanRequest(
        platform="github",
        min_length=2,
        max_length=2,
        count=3,
        include_letters=True,
        strategy="lexicographic",
    )


@pytest.mark.asyncio
async def test_job_completes_and_exposes_candidates(settings) -> None:
    manager = JobManager(settings, FakeService())
    job = manager.create(scan_request())
    for _ in range(50):
        if job.state not in {"queued", "running"}:
            break
        await asyncio.sleep(0.01)
    snapshot = job.snapshot()
    assert snapshot.state == "completed"
    assert snapshot.checked == 3
    assert len(snapshot.candidates) == 3
    await manager.aclose()


@pytest.mark.asyncio
async def test_finished_job_retention_is_bounded(settings) -> None:
    manager = JobManager(settings, FakeService())
    for _ in range(5):
        job = manager.create(scan_request())
        while job.state in {"queued", "running"}:
            await asyncio.sleep(0.005)
    manager.create(scan_request())
    assert len(manager.jobs) <= settings.max_finished_jobs + 1
    await manager.aclose()
