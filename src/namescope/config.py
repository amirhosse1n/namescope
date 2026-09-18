from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PlatformSettings:
    delay_seconds: float
    timeout_seconds: float
    cache_ttl_seconds: int


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    reload: bool
    open_browser: bool
    allow_remote: bool
    log_level: str
    database_path: Path
    max_active_jobs: int
    max_finished_jobs: int
    github: PlatformSettings
    instagram: PlatformSettings
    telegram: PlatformSettings
    github_token: str = ""
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    telegram_session: str = ""

    @property
    def is_loopback(self) -> bool:
        if self.host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _platform(data: dict[str, Any], name: str) -> PlatformSettings:
    item = data["platforms"][name]
    settings = PlatformSettings(
        delay_seconds=float(item["delay_seconds"]),
        timeout_seconds=float(item["timeout_seconds"]),
        cache_ttl_seconds=int(item["cache_ttl_seconds"]),
    )
    if settings.delay_seconds < 0 or settings.timeout_seconds <= 0 or settings.cache_ttl_seconds < 0:
        raise ValueError(f"Invalid timing configuration for {name}.")
    return settings


def _required_mapping(data: object, name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a mapping in config.yaml.")
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _required_mapping(data, "config")
    _required_mapping(root.get("app"), "app")
    _required_mapping(root.get("platforms"), "platforms")
    return root


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    config_path = Path(os.getenv("NAMESCOPE_CONFIG", str(ROOT / "config.yaml"))).expanduser()
    data = _load_yaml(config_path)
    app = data["app"]

    database_path = Path(os.getenv("NAMESCOPE_DATABASE", str(ROOT / app["database_path"]))).expanduser()
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()

    settings = Settings(
        host=os.getenv("NAMESCOPE_HOST", str(app["host"])).strip(),
        port=int(os.getenv("NAMESCOPE_PORT", app["port"])),
        reload=_bool_env("NAMESCOPE_RELOAD", bool(app["reload"])),
        open_browser=_bool_env("NAMESCOPE_OPEN_BROWSER", bool(app["open_browser"])),
        allow_remote=_bool_env("NAMESCOPE_ALLOW_REMOTE", bool(app.get("allow_remote", False))),
        log_level=os.getenv("NAMESCOPE_LOG_LEVEL", str(app["log_level"])).strip().upper(),
        database_path=database_path,
        max_active_jobs=int(app["max_active_jobs"]),
        max_finished_jobs=int(app.get("max_finished_jobs", 100)),
        github=_platform(data, "github"),
        instagram=_platform(data, "instagram"),
        telegram=_platform(data, "telegram"),
        github_token=os.getenv("GITHUB_TOKEN", os.getenv("GH_TOKEN", "")).strip(),
        telegram_api_id=int(api_id_raw) if api_id_raw.isdigit() else None,
        telegram_api_hash=os.getenv("TELEGRAM_API_HASH", "").strip(),
        telegram_session=os.getenv("TELEGRAM_SESSION", "").strip(),
    )

    if not 1 <= settings.port <= 65535:
        raise ValueError("NAMESCOPE_PORT must be between 1 and 65535.")
    if settings.max_active_jobs < 1:
        raise ValueError("max_active_jobs must be at least 1.")
    if settings.max_finished_jobs < 1:
        raise ValueError("max_finished_jobs must be at least 1.")
    if not settings.host:
        raise ValueError("NAMESCOPE_HOST cannot be empty.")

    return settings
