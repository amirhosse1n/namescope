from __future__ import annotations

import asyncio
import re
from time import perf_counter
from typing import Any

import httpx

from .. import __version__
from ..config import Settings
from ..models import CheckResult, CheckStatus
from .common import BaseChecker

_TAKEN_MARKERS = (
    'class="tgme_page_title"',
    "class='tgme_page_title'",
    'class="tgme_page_photo"',
    "class='tgme_page_photo'",
    'class="tgme_page_extra"',
    "class='tgme_page_extra'",
)
_GENERIC_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']\s*Telegram\s*["\']',
    re.IGNORECASE,
)
_GENERIC_TITLE = re.compile(r"<title[^>]*>\s*Telegram\s*</title>", re.IGNORECASE)


def classify_public_telegram(status_code: int, body: str) -> CheckStatus:
    if status_code == 429:
        return CheckStatus.RATE_LIMITED
    if status_code == 404:
        return CheckStatus.POSSIBLY_AVAILABLE
    if status_code != 200:
        return CheckStatus.UNKNOWN
    if any(marker in body for marker in _TAKEN_MARKERS):
        return CheckStatus.TAKEN
    if _GENERIC_OG_TITLE.search(body) or _GENERIC_TITLE.search(body):
        return CheckStatus.POSSIBLY_AVAILABLE
    return CheckStatus.UNKNOWN


class TelegramChecker(BaseChecker):
    platform = "telegram"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._http = httpx.AsyncClient(
            timeout=settings.telegram.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": f"NameScope/{__version__}",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            transport=transport,
        )
        self._official_client: Any = None
        self._official_authorized: bool | None = None
        self._official_lock = asyncio.Lock()

    @property
    def official_api_configured(self) -> bool:
        return bool(self.settings.telegram_api_id and self.settings.telegram_api_hash and self.settings.telegram_session)

    async def aclose(self) -> None:
        await self._http.aclose()
        if self._official_client is not None:
            try:
                await self._official_client.disconnect()
            except Exception:
                pass

    async def check(self, username: str) -> CheckResult:
        invalid = self.invalid_result(username)
        if invalid:
            return invalid

        if self.official_api_configured:
            official = await self._check_official(username)
            if official.status != CheckStatus.CONFIG_REQUIRED:
                return official

        return await self._check_public_profile(username)

    async def _ensure_official_client(self) -> tuple[Any | None, str | None]:
        if self._official_client is not None and self._official_authorized:
            return self._official_client, None

        try:
            from telethon import TelegramClient  # type: ignore
            from telethon.sessions import StringSession  # type: ignore
        except ImportError:
            return None, "Telethon is not installed. Install the telegram optional dependencies first."

        async with self._official_lock:
            if self._official_client is None:
                self._official_client = TelegramClient(
                    StringSession(self.settings.telegram_session),
                    self.settings.telegram_api_id,
                    self.settings.telegram_api_hash,
                )
                await self._official_client.connect()
                self._official_authorized = bool(await self._official_client.is_user_authorized())

        if not self._official_authorized:
            return None, "The configured Telegram session is not authorized. Run scripts/setup_telegram.py."
        return self._official_client, None

    async def _check_official(self, username: str) -> CheckResult:
        started = perf_counter()
        client, error = await self._ensure_official_client()
        if client is None:
            return self.result(username, CheckStatus.CONFIG_REQUIRED, error or "Telegram API setup is incomplete.", started)

        try:
            from telethon import errors, functions  # type: ignore

            async with self._official_lock:
                result = await client(functions.account.CheckUsernameRequest(username=username))
            if bool(result):
                return self.result(
                    username,
                    CheckStatus.AVAILABLE,
                    "Telegram's official account.checkUsername method reports this username as available.",
                    started,
                )
            return self.result(username, CheckStatus.UNKNOWN, "Telegram returned an unexpected false result.", started)
        except errors.UsernameOccupiedError:  # type: ignore[name-defined]
            return self.result(username, CheckStatus.TAKEN, "Telegram reports this username as occupied.", started)
        except errors.UsernameInvalidError:  # type: ignore[name-defined]
            return self.result(username, CheckStatus.INVALID, "Telegram reports this username as invalid.", started)
        except errors.RPCError as exc:  # type: ignore[name-defined]
            error_name = exc.__class__.__name__
            if error_name == "UsernamePurchaseAvailableError":
                return self.result(
                    username,
                    CheckStatus.PURCHASE_AVAILABLE,
                    "Telegram reports this username as purchasable through Fragment rather than freely claimable.",
                    started,
                )
            if error_name == "FloodWaitError":
                seconds = getattr(exc, "seconds", None)
                detail = "Telegram requested a flood wait."
                if seconds:
                    detail = f"Telegram requested a flood wait of {seconds} seconds."
                return self.result(username, CheckStatus.RATE_LIMITED, detail, started)
            return self.result(username, CheckStatus.ERROR, f"Telegram RPC error: {error_name}.", started)
        except Exception as exc:
            return self.result(username, CheckStatus.ERROR, f"Telegram API error: {exc.__class__.__name__}.", started)

    async def _check_public_profile(self, username: str) -> CheckResult:
        started = perf_counter()
        try:
            response = await self._http.get(f"https://t.me/{username}")
        except httpx.HTTPError as exc:
            return self.result(username, CheckStatus.ERROR, f"Telegram request failed: {exc.__class__.__name__}.", started)

        status = classify_public_telegram(response.status_code, response.text[:512_000])
        detail = {
            CheckStatus.TAKEN: "A public Telegram profile, bot, group, or channel page exists for this username.",
            CheckStatus.POSSIBLY_AVAILABLE: "No public Telegram entity was detected. It looks unclaimed, but only Telegram's authenticated account.checkUsername method can confirm free registration.",
            CheckStatus.RATE_LIMITED: "Telegram throttled the public profile request.",
            CheckStatus.UNKNOWN: "The public Telegram page could not be classified safely. Configure Telegram API credentials for a definitive check.",
        }.get(status, "The public Telegram response could not be classified safely.")
        return self.result(username, status, detail, started, response.status_code)
