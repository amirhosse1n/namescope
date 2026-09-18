from __future__ import annotations

import asyncio
from time import perf_counter
from urllib.parse import quote

import httpx

from .. import __version__
from ..config import Settings
from ..models import CheckResult, CheckStatus
from .common import BaseChecker

_GITHUB_API_VERSION = "2026-03-10"
_SIGNUP_URL = "https://github.com/signup"
_SIGNUP_CHECK_URL = "https://github.com/signup_check/username"


class GitHubChecker(BaseChecker):
    platform = "github"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        api_headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"NameScope/{__version__}",
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        }
        if settings.github_token:
            api_headers["Authorization"] = f"Bearer {settings.github_token}"

        self._api_client = httpx.AsyncClient(
            timeout=settings.github.timeout_seconds,
            follow_redirects=True,
            headers=api_headers,
            transport=transport,
        )
        self._web_client = httpx.AsyncClient(
            timeout=settings.github.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": f"NameScope/{__version__}",
                "Accept-Language": "en-US,en;q=0.9",
            },
            transport=transport,
        )
        self._signup_ready = False
        self._signup_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._api_client.aclose()
        await self._web_client.aclose()

    async def check(self, username: str) -> CheckResult:
        invalid = self.invalid_result(username)
        if invalid:
            return invalid

        started = perf_counter()
        try:
            response = await self._api_client.get(f"https://api.github.com/users/{quote(username, safe='')}")
        except httpx.HTTPError as exc:
            return self.result(username, CheckStatus.ERROR, f"GitHub request failed: {exc.__class__.__name__}.", started)

        remaining = response.headers.get("x-ratelimit-remaining")
        if response.status_code == 200:
            return self.result(
                username,
                CheckStatus.TAKEN,
                "A public GitHub account exists with this username.",
                started,
                response.status_code,
            )
        if response.status_code in {403, 429}:
            detail = "GitHub API rate limit reached."
            if remaining is not None:
                detail += f" Remaining requests: {remaining}."
            if not self.settings.github_token:
                detail += " Add GITHUB_TOKEN to increase the API quota."
            return self.result(username, CheckStatus.RATE_LIMITED, detail, started, response.status_code)
        if response.status_code != 404:
            return self.result(
                username,
                CheckStatus.UNKNOWN,
                f"GitHub returned an unexpected HTTP {response.status_code} response.",
                started,
                response.status_code,
            )

        return await self._check_signup_namespace(username, started)

    async def _prepare_signup_session(self) -> None:
        if self._signup_ready:
            return
        async with self._signup_lock:
            if self._signup_ready:
                return
            response = await self._web_client.get(
                _SIGNUP_URL,
                headers={"Accept": "text/html,application/xhtml+xml", "Referer": "https://github.com/"},
            )
            if response.status_code < 500:
                self._signup_ready = True

    async def _check_signup_namespace(self, username: str, started: float) -> CheckResult:
        try:
            await self._prepare_signup_session()
            response = await self._web_client.post(
                _SIGNUP_CHECK_URL,
                data={"value": username},
                headers={
                    "Accept": "text/html,*/*;q=0.8",
                    "Referer": _SIGNUP_URL,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except httpx.HTTPError:
            return self.result(
                username,
                CheckStatus.POSSIBLY_AVAILABLE,
                "No public GitHub account was found, but GitHub's signup check could not be completed. Verify the username manually before relying on it.",
                started,
                404,
            )

        body = response.text.strip().lower()
        if response.status_code == 200:
            return self.result(
                username,
                CheckStatus.AVAILABLE,
                "GitHub's signup availability check reports this username as available.",
                started,
                response.status_code,
            )

        unavailable_markers = (
            "already taken",
            "not available",
            "reserved word",
            "username is reserved",
            "cannot be used",
        )
        if response.status_code in {403, 409, 422} and any(marker in body for marker in unavailable_markers):
            return self.result(
                username,
                CheckStatus.UNAVAILABLE,
                "No public account resolves, but GitHub's signup check does not allow this username to be claimed.",
                started,
                response.status_code,
            )

        return self.result(
            username,
            CheckStatus.POSSIBLY_AVAILABLE,
            "No public GitHub account was found, but the signup check was inconclusive. Verify the username manually before relying on it.",
            started,
            response.status_code,
        )
