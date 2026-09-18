from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Platform = Literal["github", "instagram", "telegram"]


class CheckStatus(StrEnum):
    AVAILABLE = "available"
    POSSIBLY_AVAILABLE = "possibly_available"
    TAKEN = "taken"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    PURCHASE_AVAILABLE = "purchase_available"
    UNKNOWN = "unknown"
    RATE_LIMITED = "rate_limited"
    CONFIG_REQUIRED = "config_required"
    ERROR = "error"


class CheckResult(BaseModel):
    platform: Platform
    username: str
    status: CheckStatus
    detail: str = ""
    http_status: int | None = None
    latency_ms: int | None = None
    cached: bool = False
    checked_at: str | None = None


class QuickCheckRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    force_refresh: bool = False

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("@"):
            value = value[1:]
        return value


class ScanRequest(BaseModel):
    platform: Platform
    min_length: int = Field(ge=1, le=39)
    max_length: int = Field(ge=1, le=39)
    count: int = Field(ge=1, le=10_000)
    include_letters: bool = True
    include_digits: bool = False
    include_underscore: bool = False
    include_hyphen: bool = False
    include_period: bool = False
    custom_characters: str = Field(default="", max_length=200)
    strategy: Literal["random", "lexicographic"] = "random"
    seed: int | None = None
    force_refresh: bool = False
    recheck_previous: bool = False

    @model_validator(mode="after")
    def validate_range_and_charset(self) -> "ScanRequest":
        if self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length")
        if not any(
            (
                self.include_letters,
                self.include_digits,
                self.include_underscore,
                self.include_hyphen,
                self.include_period,
                bool(self.custom_characters),
            )
        ):
            raise ValueError("select at least one character group or provide custom characters")
        return self


class JobStartResponse(BaseModel):
    job_id: str
    platform: Platform
    requested: int


class JobSnapshot(BaseModel):
    job_id: str
    platform: Platform
    state: Literal["queued", "running", "completed", "cancelled", "failed"]
    requested: int
    generated: int
    checked: int
    counts: dict[str, int]
    results: list[CheckResult]
    candidates: list[CheckResult] = Field(default_factory=list)
    message: str | None = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
