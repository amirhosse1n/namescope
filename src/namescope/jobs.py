from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .config import Settings
from .generator import generate_candidates
from .models import CheckResult, CheckStatus, JobSnapshot, ScanRequest
from .service import CheckService

logger = logging.getLogger("namescope.jobs")

CANDIDATE_STATUSES = {
    CheckStatus.AVAILABLE,
    CheckStatus.POSSIBLY_AVAILABLE,
    CheckStatus.PURCHASE_AVAILABLE,
}
_FINISHED_STATES = {"completed", "cancelled", "failed"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ScanJob:
    job_id: str
    request: ScanRequest
    state: str = "queued"
    generated: int = 0
    checked: int = 0
    results: deque[CheckResult] = field(default_factory=lambda: deque(maxlen=500))
    candidates: deque[CheckResult] = field(default_factory=lambda: deque(maxlen=1000))
    counts: Counter[str] = field(default_factory=Counter)
    message: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    cancelled: bool = False

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot(
            job_id=self.job_id,
            platform=self.request.platform,
            state=self.state,  # type: ignore[arg-type]
            requested=self.request.count,
            generated=self.generated,
            checked=self.checked,
            counts=dict(self.counts),
            results=list(self.results),
            candidates=list(self.candidates),
            message=self.message,
            error=self.error,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )


class JobManager:
    def __init__(self, settings: Settings, service: CheckService) -> None:
        self.settings = settings
        self.service = service
        self.jobs: dict[str, ScanJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._semaphore = asyncio.Semaphore(settings.max_active_jobs)

    def create(self, request: ScanRequest) -> ScanJob:
        self._prune_finished()
        job = ScanJob(job_id=uuid.uuid4().hex[:12], request=request)
        self.jobs[job.job_id] = job
        task = asyncio.create_task(self._run(job), name=f"namescope-scan-{job.job_id}")
        self._tasks[job.job_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.job_id, None))
        return job

    def get(self, job_id: str) -> ScanJob | None:
        return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.state not in {"queued", "running"}:
            return False
        job.cancelled = True
        return True

    async def aclose(self) -> None:
        for job in self.jobs.values():
            if job.state in {"queued", "running"}:
                job.cancelled = True
        pending = list(self._tasks.values())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _prune_finished(self) -> None:
        finished = [job for job in self.jobs.values() if job.state in _FINISHED_STATES]
        overflow = len(finished) - self.settings.max_finished_jobs + 1
        if overflow <= 0:
            return
        finished.sort(key=lambda job: job.finished_at or job.started_at or "")
        for job in finished[:overflow]:
            self.jobs.pop(job.job_id, None)

    @staticmethod
    def _finish_cancelled(job: ScanJob) -> None:
        job.state = "cancelled"
        job.message = "Scan cancelled."
        job.finished_at = _now()

    async def _run(self, job: ScanJob) -> None:
        async with self._semaphore:
            try:
                if job.cancelled:
                    self._finish_cancelled(job)
                    return

                job.state = "running"
                job.started_at = _now()
                excluded: set[str] = set()
                if not job.request.recheck_previous:
                    excluded = self.service.store.seen_usernames(job.request.platform)

                candidates = generate_candidates(job.request, excluded=excluded)
                job.generated = len(candidates)
                delay = getattr(self.settings, job.request.platform).delay_seconds
                force_refresh = job.request.force_refresh or job.request.recheck_previous

                for index, username in enumerate(candidates):
                    if job.cancelled:
                        self._finish_cancelled(job)
                        return
                    if index and delay > 0:
                        await asyncio.sleep(delay)
                        if job.cancelled:
                            self._finish_cancelled(job)
                            return

                    result = await self.service.check(job.request.platform, username, force_refresh=force_refresh)
                    job.results.append(result)
                    if result.status in CANDIDATE_STATUSES:
                        job.candidates.append(result)
                    job.checked += 1
                    job.counts[result.status.value] += 1

                    if result.status == CheckStatus.RATE_LIMITED:
                        job.message = "Scan stopped after the platform returned a rate-limit response."
                        break

                job.state = "completed"
                job.finished_at = _now()
            except Exception:
                logger.exception("Scan job %s failed", job.job_id)
                job.state = "failed"
                job.error = "Scan failed. Check the server log for details."
                job.finished_at = _now()
