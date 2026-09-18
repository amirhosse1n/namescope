from __future__ import annotations

import asyncio
import json
import re
from time import perf_counter
from typing import Any

import httpx

from ..config import Settings
from ..models import CheckResult, CheckStatus
from .common import BaseChecker

_PROFILE_INDICATORS = (
    "instagram://user?username=",
    '"@type":"ProfilePage"',
    '"profile_pic_url"',
    '"edge_followed_by"',
)
_NOT_FOUND_INDICATORS = (
    "sorry, this page isn't available",
    "the link you followed may be broken",
    "page may have been removed",
    "page isn't available",
)
_LOGIN_WALL_INDICATORS = (
    "/accounts/login/",
    "loginform",
    "challenge_required",
    "please wait a few minutes before you try again",
)
_GENERIC_TITLE_RE = re.compile(r"<title[^>]*>\s*Instagram\s*</title>", re.IGNORECASE)
_PROFILE_META_RE = re.compile(r'property=["\'](?:og:title|og:description|al:ios:url)["\']', re.IGNORECASE)
_PROFILE_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:(?:title|description)["\'][^>]+content=["\'][^"\']*@[^"\']+',
    re.IGNORECASE,
)

_WEB_PROFILE_INFO_URL = "https://www.instagram.com/api/v1/users/web_profile_info/"
_PUBLIC_WEB_APP_ID = "936619743392459"
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def classify_instagram_html(status_code: int, body: str, final_url: str = "") -> CheckStatus:
    lower = body.lower()
    if status_code == 429:
        return CheckStatus.RATE_LIMITED
    if status_code == 404:
        return CheckStatus.POSSIBLY_AVAILABLE
    if status_code in {401, 403} or status_code != 200:
        return CheckStatus.UNKNOWN
    if "/accounts/login" in final_url.lower() or any(marker in lower for marker in _LOGIN_WALL_INDICATORS):
        return CheckStatus.UNKNOWN
    if _PROFILE_OG_RE.search(body) or any(marker.lower() in lower for marker in _PROFILE_INDICATORS):
        return CheckStatus.TAKEN
    if any(marker in lower for marker in _NOT_FOUND_INDICATORS):
        return CheckStatus.POSSIBLY_AVAILABLE
    if _GENERIC_TITLE_RE.search(body) and not _PROFILE_META_RE.search(body):
        return CheckStatus.POSSIBLY_AVAILABLE
    return CheckStatus.UNKNOWN


def classify_instagram_profile_info(status_code: int, payload: Any) -> CheckStatus:
    if status_code == 429:
        return CheckStatus.RATE_LIMITED
    if status_code == 404:
        return CheckStatus.POSSIBLY_AVAILABLE
    if status_code != 200 or not isinstance(payload, dict):
        return CheckStatus.UNKNOWN

    data = payload.get("data")
    if not isinstance(data, dict):
        return CheckStatus.UNKNOWN

    user = data.get("user")
    if isinstance(user, dict) and (user.get("username") or user.get("id")):
        return CheckStatus.TAKEN
    if "user" in data and user is None:
        return CheckStatus.POSSIBLY_AVAILABLE
    return CheckStatus.UNKNOWN


class InstagramChecker(BaseChecker):
    platform = "instagram"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.instagram.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": _BROWSER_USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
            transport=transport,
        )
        self._bootstrapped = False
        self._bootstrap_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def check(self, username: str) -> CheckResult:
        invalid = self.invalid_result(username)
        if invalid:
            return invalid

        started = perf_counter()
        try:
            api_result = await self._check_profile_info(username)
            if api_result is not None:
                status, http_status, detail = api_result
                return self.result(username, status, detail, started, http_status)

            response = await self._client.get(
                f"https://www.instagram.com/{username}/",
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://www.instagram.com/",
                },
            )
        except httpx.HTTPError as exc:
            return self.result(username, CheckStatus.ERROR, f"Instagram request failed: {exc.__class__.__name__}.", started)

        status = classify_instagram_html(response.status_code, response.text[:512_000], str(response.url))
        detail = {
            CheckStatus.TAKEN: "Instagram returned public profile markers for this username.",
            CheckStatus.POSSIBLY_AVAILABLE: "No public Instagram profile was detected. Instagram may still reserve or restrict the username, so verify it in the app before relying on it.",
            CheckStatus.RATE_LIMITED: "Instagram throttled the public profile request. Slow down and try again later.",
            CheckStatus.UNKNOWN: "Instagram returned a login, interstitial, or unrecognized page, so the username could not be classified safely.",
        }.get(status, f"Instagram returned HTTP {response.status_code}, which could not be classified safely.")
        return self.result(username, status, detail, started, response.status_code)

    async def _bootstrap(self) -> None:
        if self._bootstrapped:
            return
        async with self._bootstrap_lock:
            if self._bootstrapped:
                return
            try:
                response = await self._client.get(
                    "https://www.instagram.com/",
                    headers={"Accept": "text/html,application/xhtml+xml"},
                )
                if response.status_code < 500:
                    self._bootstrapped = True
            except httpx.HTTPError:
                return

    async def _profile_info_response(self, username: str) -> httpx.Response:
        return await self._client.get(
            _WEB_PROFILE_INFO_URL,
            params={"username": username},
            headers={
                "Accept": "*/*",
                "X-IG-App-ID": _PUBLIC_WEB_APP_ID,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://www.instagram.com/{username}/",
            },
        )

    async def _check_profile_info(self, username: str) -> tuple[CheckStatus, int, str] | None:
        response = await self._profile_info_response(username)
        if response.status_code in {400, 401, 403} and not self._bootstrapped:
            await self._bootstrap()
            if self._bootstrapped:
                response = await self._profile_info_response(username)

        if response.status_code == 429:
            return (
                CheckStatus.RATE_LIMITED,
                response.status_code,
                "Instagram throttled the public profile lookup. Slow down and try again later.",
            )

        payload: Any = None
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            payload = None

        status = classify_instagram_profile_info(response.status_code, payload)
        if status == CheckStatus.TAKEN:
            return (
                status,
                response.status_code,
                "Instagram's public web profile lookup returned a user for this username.",
            )
        if status == CheckStatus.POSSIBLY_AVAILABLE:
            return (
                status,
                response.status_code,
                "Instagram's public web profile lookup found no user. Treat this as a candidate, not a registration guarantee.",
            )
        return None
