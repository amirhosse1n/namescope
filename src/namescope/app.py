from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, load_settings
from .generator import validate_generation_request
from .jobs import JobManager
from .models import JobSnapshot, JobStartResponse, Platform, QuickCheckRequest, ScanRequest
from .rules import rule_payload
from .service import CheckService
from .storage import ResultStore

logger = logging.getLogger("namescope")
static_dir = Path(__file__).parent / "web" / "static"


@dataclass
class AppContext:
    settings: Settings
    store: ResultStore
    service: CheckService
    jobs: JobManager


_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _context(request: Request) -> AppContext:
    return request.app.state.context


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = ResultStore(resolved.database_path)
        service = CheckService(resolved, store)
        jobs = JobManager(resolved, service)
        app.state.context = AppContext(resolved, store, service, jobs)
        try:
            yield
        finally:
            await jobs.aclose()
            await service.aclose()

    app = FastAPI(title="NameScope", version=__version__, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, object]:
        ctx = _context(request)
        return {
            "status": "ok",
            "name": "NameScope",
            "version": __version__,
            "github_authenticated": bool(ctx.settings.github_token),
            "telegram_official_api": ctx.service.telegram.official_api_configured,
        }

    @app.get("/api/rules")
    async def rules() -> dict[str, dict[str, object]]:
        return rule_payload()

    @app.post("/api/check")
    async def quick_check(payload: QuickCheckRequest, request: Request) -> dict[str, object]:
        results = await _context(request).service.quick_check(payload.username, payload.force_refresh)
        return {
            "username": payload.username.lower(),
            "results": [item.model_dump(mode="json") for item in results],
        }

    @app.get("/api/history/{platform}")
    async def history(
        platform: Platform,
        request: Request,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        store = _context(request).store
        return {
            "platform": platform,
            "count": store.history_count(platform),
            "items": store.recent_history(platform, limit),
        }

    @app.delete("/api/history/{platform}")
    async def reset_history(platform: Platform, request: Request) -> dict[str, object]:
        removed = _context(request).store.reset_platform(platform)
        return {"platform": platform, "removed": removed, "count": 0}

    @app.post("/api/scans", response_model=JobStartResponse)
    async def start_scan(payload: ScanRequest, request: Request) -> JobStartResponse:
        errors = validate_generation_request(payload)
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        job = _context(request).jobs.create(payload)
        return JobStartResponse(job_id=job.job_id, platform=payload.platform, requested=payload.count)

    @app.get("/api/scans/{job_id}", response_model=JobSnapshot)
    async def scan_status(job_id: str, request: Request) -> JobSnapshot:
        job = _context(request).jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Scan job not found")
        return job.snapshot()

    @app.post("/api/scans/{job_id}/cancel")
    async def cancel_scan(job_id: str, request: Request) -> dict[str, bool]:
        if not _context(request).jobs.cancel(job_id):
            raise HTTPException(status_code=409, detail="Scan is not running or does not exist")
        return {"cancelled": True}

    return app


app = create_app()
