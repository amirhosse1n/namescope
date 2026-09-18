from datetime import UTC, datetime

from namescope.models import CheckResult, CheckStatus
from namescope.storage import ResultStore


def result(status: CheckStatus, username: str = "abc") -> CheckResult:
    return CheckResult(
        platform="github",
        username=username,
        status=status,
        detail="detail",
        checked_at=datetime.now(UTC).isoformat(),
    )


def test_store_persists_history_and_cache(tmp_path) -> None:
    store = ResultStore(tmp_path / "db.sqlite3")
    store.save(result(CheckStatus.TAKEN))
    assert store.history_count("github") == 1
    cached = store.get_cached("github", "abc", 60)
    assert cached is not None
    assert cached.status == CheckStatus.TAKEN
    assert cached.cached is True


def test_uncertain_result_is_history_only(tmp_path) -> None:
    store = ResultStore(tmp_path / "db.sqlite3")
    store.save(result(CheckStatus.UNKNOWN))
    assert store.history_count("github") == 1
    assert store.get_cached("github", "abc", 60) is None


def test_reset_platform_removes_cache_and_history(tmp_path) -> None:
    store = ResultStore(tmp_path / "db.sqlite3")
    store.save(result(CheckStatus.TAKEN))
    assert store.reset_platform("github") == 1
    assert store.history_count("github") == 0
    assert store.get_cached("github", "abc", 60) is None


def test_legacy_github_available_migration_runs_once(tmp_path) -> None:
    path = tmp_path / "db.sqlite3"
    store = ResultStore(path)
    store.save(result(CheckStatus.AVAILABLE, "fresh"))

    reopened = ResultStore(path)
    cached = reopened.get_cached("github", "fresh", 60)
    assert cached is not None
    assert cached.status == CheckStatus.AVAILABLE
