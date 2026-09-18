import httpx
import pytest

from namescope.checkers.github import GitHubChecker
from namescope.models import CheckStatus


@pytest.mark.asyncio
async def test_github_taken(settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.github.com"
        return httpx.Response(200, json={"login": "octocat"})

    checker = GitHubChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("octocat")
        assert result.status == CheckStatus.TAKEN
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_github_signup_check_confirms_available(settings) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.host, request.url.path))
        if request.url.host == "api.github.com":
            return httpx.Response(404)
        if request.url.path == "/signup":
            return httpx.Response(200, headers={"set-cookie": "logged_in=no; Path=/"})
        if request.url.path == "/signup_check/username":
            assert request.method == "POST"
            assert request.content == b"value=qzx"
            return httpx.Response(200, text="")
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    checker = GitHubChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("qzx")
        assert result.status == CheckStatus.AVAILABLE
        assert ("POST", "github.com", "/signup_check/username") in calls
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_github_signup_check_rejects_reserved_name(settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(404)
        if request.url.path == "/signup":
            return httpx.Response(200)
        return httpx.Response(403, text="Username is a reserved word")

    checker = GitHubChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("reserved")
        assert result.status == CheckStatus.UNAVAILABLE
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_github_inconclusive_signup_response_stays_likely(settings) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(404)
        if request.url.path == "/signup":
            return httpx.Response(406)
        return httpx.Response(403, text="Please enable cookies")

    checker = GitHubChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("qzx")
        assert result.status == CheckStatus.POSSIBLY_AVAILABLE
    finally:
        await checker.aclose()


@pytest.mark.asyncio
async def test_github_rate_limit(settings) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"})

    checker = GitHubChecker(settings, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("abc")
        assert result.status == CheckStatus.RATE_LIMITED
    finally:
        await checker.aclose()

@pytest.mark.asyncio
async def test_github_token_is_not_sent_to_web_signup(settings_with_github_token) -> None:
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "api.github.com":
            return httpx.Response(404)
        if request.url.path == "/signup":
            return httpx.Response(200)
        return httpx.Response(200)

    checker = GitHubChecker(settings_with_github_token, transport=httpx.MockTransport(handler))
    try:
        result = await checker.check("qzx")
        assert result.status == CheckStatus.AVAILABLE
        assert ("api.github.com", "Bearer test-token") in seen
        assert all(auth is None for host, auth in seen if host == "github.com")
    finally:
        await checker.aclose()
