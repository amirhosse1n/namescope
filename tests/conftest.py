from __future__ import annotations

from dataclasses import replace

import pytest

from namescope.config import PlatformSettings, Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    platform = PlatformSettings(delay_seconds=0, timeout_seconds=2, cache_ttl_seconds=60)
    return Settings(
        host="127.0.0.1",
        port=8765,
        reload=False,
        open_browser=False,
        allow_remote=False,
        log_level="INFO",
        database_path=tmp_path / "namescope.sqlite3",
        max_active_jobs=2,
        max_finished_jobs=3,
        github=platform,
        instagram=platform,
        telegram=platform,
    )


@pytest.fixture
def settings_with_github_token(settings: Settings) -> Settings:
    return replace(settings, github_token="test-token")
