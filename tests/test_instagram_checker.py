import httpx
import pytest

from namescope.checkers.instagram import InstagramChecker, classify_instagram_html, classify_instagram_profile_info
from namescope.models import CheckStatus


def test_instagram_profile_info_classifier() -> None:
    assert classify_instagram_profile_info(200, {"data": {"user": {"id": "1", "username": "taken"}}}) == CheckStatus.TAKEN
    assert classify_instagram_profile_info(200, {"data": {"user": None}}) == CheckStatus.POSSIBLY_AVAILABLE
    assert classify_instagram_profile_info(200, {"data": {}}) == CheckStatus.UNKNOWN
    assert classify_instagram_profile_info(429, {}) == CheckStatus.RATE_LIMITED


def test_instagram_html_classifier() -> None:
    assert classify_instagram_html(404, "") == CheckStatus.POSSIBLY_AVAILABLE
    assert classify_instagram_html(200, '<title>Instagram</title>') == CheckStatus.POSSIBLY_AVAILABLE
    assert classify_instagram_html(200, '"profile_pic_url":"x"') == CheckStatus.TAKEN
    assert classify_instagram_html(200, "loginForm") == CheckStatus.UNKNOWN


@pytest.mark.asyncio
async def test_instagram_json_lookup_taken(settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/users/web_profile_info/"
        return httpx.Response(200, json={"data": {"user": {"id": "1", "username": "taken"}}})

    checker = InstagramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("taken")
        assert result.status == CheckStatus.TAKEN
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_instagram_json_lookup_missing(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"user": None}})

    checker = InstagramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("qzx")
        assert result.status == CheckStatus.POSSIBLY_AVAILABLE
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_instagram_bootstrap_then_html_fallback(settings) -> None:
    calls = {"profile": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users/web_profile_info/":
            calls["profile"] += 1
            return httpx.Response(403)
        if request.url.path == "/" and request.url.host == "www.instagram.com":
            return httpx.Response(200, text="<html></html>")
        if request.url.path == "/qzx/":
            return httpx.Response(200, text="<title>Instagram</title>")
        raise AssertionError(str(request.url))

    checker = InstagramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("qzx")
        assert calls["profile"] == 2
        assert result.status == CheckStatus.POSSIBLY_AVAILABLE
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_instagram_all_digits_are_rejected_before_network(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Network should not be called for invalid input")

    checker = InstagramChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("122")
        assert result.status == CheckStatus.INVALID
    finally:
        await checker.aclose()
