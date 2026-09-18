from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .checkers import GitHubChecker, InstagramChecker, TelegramChecker
from .config import Settings
from .models import CheckResult, Platform
from .storage import ResultStore

CheckerFn = Callable[[str], Awaitable[CheckResult]]


class CheckService:
    def __init__(
        self,
        settings: Settings,
        store: ResultStore,
        github: GitHubChecker | None = None,
        instagram: InstagramChecker | None = None,
        telegram: TelegramChecker | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.github = github or GitHubChecker(settings)
        self.instagram = instagram or InstagramChecker(settings)
        self.telegram = telegram or TelegramChecker(settings)

    def _ttl(self, platform: Platform) -> int:
        return getattr(self.settings, platform).cache_ttl_seconds

    def _checker(self, platform: Platform) -> CheckerFn:
        return getattr(self, platform).check

    async def check(self, platform: Platform, username: str, force_refresh: bool = False) -> CheckResult:
        normalized = username.strip().lstrip("@").lower()
        if not force_refresh:
            cached = self.store.get_cached(platform, normalized, self._ttl(platform))
            if cached:
                self.store.record_history(cached)
                return cached

        result = await self._checker(platform)(normalized)
        self.store.save(result)
        return result

    async def quick_check(self, username: str, force_refresh: bool = False) -> list[CheckResult]:
        return list(
            await asyncio.gather(
                self.check("github", username, force_refresh),
                self.check("instagram", username, force_refresh),
                self.check("telegram", username, force_refresh),
            )
        )

    async def aclose(self) -> None:
        await asyncio.gather(
            self.github.aclose(),
            self.instagram.aclose(),
            self.telegram.aclose(),
        )
