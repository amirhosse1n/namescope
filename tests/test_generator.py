import pytest

from namescope.generator import generate_candidates, validate_generation_request
from namescope.models import ScanRequest
from namescope.rules import validate_username


def request(platform: str = "github", **overrides) -> ScanRequest:
    payload = {
        "platform": platform,
        "min_length": 3 if platform != "telegram" else 5,
        "max_length": 3 if platform != "telegram" else 5,
        "count": 25,
        "include_letters": True,
        "include_digits": False,
        "include_underscore": False,
        "include_hyphen": False,
        "include_period": False,
        "custom_characters": "",
        "strategy": "random",
        "seed": 7,
    }
    payload.update(overrides)
    return ScanRequest(**payload)


def test_random_generation_is_unique_and_valid() -> None:
    req = request(include_digits=True, count=100)
    candidates = generate_candidates(req)
    assert len(candidates) == 100
    assert len(set(candidates)) == 100
    assert all(validate_username("github", value).valid for value in candidates)


def test_history_exclusion_prevents_repeats() -> None:
    req = request(strategy="lexicographic", count=3)
    assert generate_candidates(req, excluded={"aaa", "aab"}) == ["aac", "aad", "aae"]


def test_instagram_generation_never_returns_all_digits() -> None:
    req = request("instagram", include_digits=True, count=250)
    candidates = generate_candidates(req)
    assert all(not value.isdigit() for value in candidates)


def test_instagram_digits_only_search_space_is_rejected() -> None:
    req = request("instagram", include_letters=False, include_digits=True)
    errors = validate_generation_request(req)
    assert any("non-digit" in error for error in errors)


def test_telegram_incompatible_character_group_is_rejected() -> None:
    req = request("telegram", include_period=True)
    assert validate_generation_request(req)


def test_tiny_search_space_reports_exhaustion() -> None:
    req = request(min_length=1, max_length=1, count=2, include_letters=False, custom_characters="a")
    with pytest.raises(ValueError, match="Only 1"):
        generate_candidates(req)
