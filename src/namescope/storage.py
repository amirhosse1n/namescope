from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import CheckResult, CheckStatus, Platform

_NON_REUSABLE = {
    CheckStatus.ERROR,
    CheckStatus.RATE_LIMITED,
    CheckStatus.UNKNOWN,
    CheckStatus.CONFIG_REQUIRED,
}


class ResultStore:
    """SQLite-backed result cache and durable per-platform history."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checks (
                    platform TEXT NOT NULL,
                    username TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    http_status INTEGER,
                    latency_ms INTEGER,
                    checked_at TEXT NOT NULL,
                    PRIMARY KEY(platform, username)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    platform TEXT NOT NULL,
                    username TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    http_status INTEGER,
                    latency_ms INTEGER,
                    first_checked_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(platform, username)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_platform ON history(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_last_checked ON history(platform, last_checked_at DESC)")
            self._run_migrations(conn)
            self._backfill_history(conn)

    @classmethod
    def _run_migrations(cls, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
        version = int(row["value"]) if row else 0
        if version < 1:
            cls._migrate_legacy_github_availability(conn)
            conn.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )

    @staticmethod
    def _migrate_legacy_github_availability(conn: sqlite3.Connection) -> None:
        detail = (
            "No public GitHub account was found. Public profile absence alone does not prove that the namespace is claimable."
        )
        params = (CheckStatus.POSSIBLY_AVAILABLE.value, detail, CheckStatus.AVAILABLE.value)
        conn.execute(
            "UPDATE checks SET status = ?, detail = ? WHERE platform = 'github' AND status = ?",
            params,
        )
        conn.execute(
            "UPDATE history SET status = ?, detail = ? WHERE platform = 'github' AND status = ?",
            params,
        )

    @staticmethod
    def _backfill_history(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO history(
                platform, username, status, detail, http_status, latency_ms,
                first_checked_at, last_checked_at, attempts
            )
            SELECT platform, username, status, detail, http_status, latency_ms,
                   checked_at, checked_at, 1
            FROM checks
            """
        )

    def get_cached(self, platform: Platform, username: str, ttl_seconds: int) -> CheckResult | None:
        key = username.lower()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM checks WHERE platform = ? AND username = ?",
                (platform, key),
            ).fetchone()

        if not row:
            return None

        checked_at = datetime.fromisoformat(row["checked_at"])
        if datetime.now(UTC) - checked_at > timedelta(seconds=ttl_seconds):
            return None

        return CheckResult(
            platform=platform,
            username=key,
            status=CheckStatus(row["status"]),
            detail=row["detail"],
            http_status=row["http_status"],
            latency_ms=row["latency_ms"],
            checked_at=row["checked_at"],
            cached=True,
        )

    def save(self, result: CheckResult) -> None:
        self.record_history(result)
        if result.status in _NON_REUSABLE:
            return

        checked_at = result.checked_at or datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checks(platform, username, status, detail, http_status, latency_ms, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, username) DO UPDATE SET
                    status=excluded.status,
                    detail=excluded.detail,
                    http_status=excluded.http_status,
                    latency_ms=excluded.latency_ms,
                    checked_at=excluded.checked_at
                """,
                (
                    result.platform,
                    result.username.lower(),
                    result.status.value,
                    result.detail,
                    result.http_status,
                    result.latency_ms,
                    checked_at,
                ),
            )

    def record_history(self, result: CheckResult) -> None:
        checked_at = result.checked_at or datetime.now(UTC).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history(
                    platform, username, status, detail, http_status, latency_ms,
                    first_checked_at, last_checked_at, attempts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(platform, username) DO UPDATE SET
                    status=excluded.status,
                    detail=excluded.detail,
                    http_status=excluded.http_status,
                    latency_ms=excluded.latency_ms,
                    last_checked_at=excluded.last_checked_at,
                    attempts=history.attempts + 1
                """,
                (
                    result.platform,
                    result.username.lower(),
                    result.status.value,
                    result.detail,
                    result.http_status,
                    result.latency_ms,
                    checked_at,
                    checked_at,
                ),
            )

    def seen_usernames(self, platform: Platform) -> set[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT username FROM history WHERE platform = ?", (platform,)).fetchall()
        return {str(row["username"]) for row in rows}

    def history_count(self, platform: Platform) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM history WHERE platform = ?", (platform,)).fetchone()
        return int(row["count"] if row else 0)

    def recent_history(self, platform: Platform, limit: int = 100) -> list[dict[str, object]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, status, detail, http_status, latency_ms,
                       first_checked_at, last_checked_at, attempts
                FROM history
                WHERE platform = ?
                ORDER BY last_checked_at DESC
                LIMIT ?
                """,
                (platform, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def reset_platform(self, platform: Platform) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM history WHERE platform = ?", (platform,)).fetchone()
            removed = int(row["count"] if row else 0)
            conn.execute("DELETE FROM history WHERE platform = ?", (platform,))
            conn.execute("DELETE FROM checks WHERE platform = ?", (platform,))
        return removed
