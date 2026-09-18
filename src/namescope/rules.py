from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Platform


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str = ""


@dataclass(frozen=True)
class PlatformRule:
    platform: Platform
    min_length: int
    max_length: int
    allowed_groups: tuple[str, ...]
    summary: str


RULES: dict[Platform, PlatformRule] = {
    "github": PlatformRule(
        platform="github",
        min_length=1,
        max_length=39,
        allowed_groups=("letters", "digits", "hyphen"),
        summary="1–39 characters; letters, digits, and single hyphens; no leading, trailing, or consecutive hyphens.",
    ),
    "instagram": PlatformRule(
        platform="instagram",
        min_length=1,
        max_length=30,
        allowed_groups=("letters", "digits", "underscore", "period"),
        summary="1–30 characters; letters, digits, underscores, and periods; no edge/consecutive periods; all-digit candidates are excluded.",
    ),
    "telegram": PlatformRule(
        platform="telegram",
        min_length=5,
        max_length=32,
        allowed_groups=("letters", "digits", "underscore"),
        summary="5–32 characters; Latin letters, digits, and underscores; start with a letter and do not end with an underscore.",
    ),
}

_GITHUB_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
_INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9_](?:[A-Za-z0-9_]|\.(?!\.)){0,28}[A-Za-z0-9_]$|^[A-Za-z0-9_]$")
_TELEGRAM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,30}[A-Za-z0-9]$")


def validate_username(platform: Platform, username: str) -> ValidationResult:
    if not username:
        return ValidationResult(False, "Username is empty.")

    rule = RULES[platform]
    if not rule.min_length <= len(username) <= rule.max_length:
        return ValidationResult(False, f"Length must be between {rule.min_length} and {rule.max_length} characters.")

    if platform == "github":
        if not _GITHUB_RE.fullmatch(username):
            return ValidationResult(False, "Use letters, digits, or single hyphens; a hyphen cannot lead, trail, or repeat.")
    elif platform == "instagram":
        if not _INSTAGRAM_RE.fullmatch(username):
            return ValidationResult(False, "Use letters, digits, underscores, or periods; periods cannot lead, trail, or repeat.")
        if username.isdigit():
            return ValidationResult(False, "NameScope excludes Instagram usernames made only of digits.")
    elif platform == "telegram":
        if not _TELEGRAM_RE.fullmatch(username):
            return ValidationResult(False, "Use 5–32 Latin letters, digits, or underscores; start with a letter and do not end with an underscore.")

    return ValidationResult(True)


def rule_payload() -> dict[str, dict[str, object]]:
    return {
        name: {
            "min_length": rule.min_length,
            "max_length": rule.max_length,
            "allowed_groups": list(rule.allowed_groups),
            "summary": rule.summary,
        }
        for name, rule in RULES.items()
    }
