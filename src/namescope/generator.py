from __future__ import annotations

import itertools
import random
import string
from collections.abc import Collection, Iterator

from .models import Platform, ScanRequest
from .rules import RULES, validate_username

GROUPS = {
    "letters": string.ascii_lowercase,
    "digits": string.digits,
    "underscore": "_",
    "hyphen": "-",
    "period": ".",
}


def build_alphabet(request: ScanRequest) -> str:
    chars = ""
    if request.include_letters:
        chars += GROUPS["letters"]
    if request.include_digits:
        chars += GROUPS["digits"]
    if request.include_underscore:
        chars += GROUPS["underscore"]
    if request.include_hyphen:
        chars += GROUPS["hyphen"]
    if request.include_period:
        chars += GROUPS["period"]
    chars += request.custom_characters.lower()
    return "".join(dict.fromkeys(chars))


def validate_generation_request(request: ScanRequest) -> list[str]:
    errors: list[str] = []
    rule = RULES[request.platform]

    if request.min_length < rule.min_length or request.max_length > rule.max_length:
        errors.append(f"{request.platform.title()} supports lengths {rule.min_length}–{rule.max_length} in NameScope.")

    allowed = set(GROUPS["letters"] + GROUPS["digits"])
    for group, char in (("underscore", "_"), ("hyphen", "-"), ("period", ".")):
        if group in rule.allowed_groups:
            allowed.add(char)

    alphabet = build_alphabet(request)
    invalid_chars = sorted(set(alphabet) - allowed)
    if invalid_chars:
        errors.append(f"Unsupported characters for {request.platform.title()}: {' '.join(invalid_chars)}")
    if not alphabet:
        errors.append("The selected alphabet is empty.")
    if request.platform == "instagram" and alphabet and all(char in string.digits for char in alphabet):
        errors.append("Instagram scans need at least one non-digit character in the selected alphabet.")

    return errors


def _lexicographic(platform: Platform, alphabet: str, min_length: int, max_length: int) -> Iterator[str]:
    for length in range(min_length, max_length + 1):
        for parts in itertools.product(alphabet, repeat=length):
            candidate = "".join(parts)
            if validate_username(platform, candidate).valid:
                yield candidate


def _random_candidates(request: ScanRequest, alphabet: str, excluded: set[str]) -> Iterator[str]:
    rng = random.Random(request.seed)
    seen: set[str] = set()
    yielded = 0
    attempts = 0
    attempt_limit = max(5_000, request.count * 120)

    while yielded < request.count and attempts < attempt_limit:
        attempts += 1
        length = rng.randint(request.min_length, request.max_length)
        candidate = "".join(rng.choice(alphabet) for _ in range(length))
        if candidate in seen or candidate in excluded or not validate_username(request.platform, candidate).valid:
            continue
        seen.add(candidate)
        yielded += 1
        yield candidate

    if yielded >= request.count:
        return

    for candidate in _lexicographic(request.platform, alphabet, request.min_length, request.max_length):
        if candidate in seen or candidate in excluded:
            continue
        seen.add(candidate)
        yielded += 1
        yield candidate
        if yielded >= request.count:
            return


def generate_candidates(request: ScanRequest, excluded: Collection[str] | None = None) -> list[str]:
    errors = validate_generation_request(request)
    if errors:
        raise ValueError(" ".join(errors))

    excluded_set = {value.lower() for value in (excluded or ())}
    alphabet = build_alphabet(request)

    if request.strategy == "lexicographic":
        iterator = (
            candidate
            for candidate in _lexicographic(request.platform, alphabet, request.min_length, request.max_length)
            if candidate not in excluded_set
        )
    else:
        iterator = _random_candidates(request, alphabet, excluded_set)

    candidates = list(itertools.islice(iterator, request.count))
    if len(candidates) < request.count:
        suffix = " after excluding previously checked usernames" if excluded_set else ""
        raise ValueError(
            f"Only {len(candidates)} new unique valid usernames are available in the selected search space{suffix}. "
            "Reduce the requested count, expand the search space, or enable rechecking previous usernames."
        )
    return candidates
