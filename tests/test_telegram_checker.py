import httpx
import pytest

from namescope.checkers.telegram import TelegramChecker, classify_public_telegram
from namescope.models import CheckStatus


def test_public_telegram_classifier() -> None:
    assert classify_public_telegram(200, '<div class="tgme_page_title">Name</div>') == CheckStatus.TAKEN
    assert classify_public_telegram(200, "<title>Telegram</title>") == CheckStatus.POSSIBLY_AVAILABLE
    assert classify_public_telegram(404, "") == CheckStatus.POSSIBLY_AVAILABLE
    assert classify_public_telegram(429, "") == CheckStatus.RATE_LIMITED


@pytest.mark.asyncio
async def test_public_telegram_taken(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='<div class="tgme_page_title">Name</div>')

    checker = TelegramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("abcde")
        assert result.status == CheckStatus.TAKEN
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_public_telegram_likely_unclaimed(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<title>Telegram</title>")

    checker = TelegramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("abcde")
        assert result.status == CheckStatus.POSSIBLY_AVAILABLE
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_telegram_invalid_starting_digit_skips_network(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Network should not be called for invalid input")

    checker = TelegramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("1abcd")
        assert result.status == CheckStatus.INVALID
    finally:
        await checker.aclose()
