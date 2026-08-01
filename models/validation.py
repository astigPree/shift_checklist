"""Validation and serialization helpers shared by domain models."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time
from enum import Enum
from typing import Any, TypeVar
from uuid import UUID


class ModelValidationError(ValueError):
    """Raised when persisted or user-provided model data is invalid."""


EnumType = TypeVar("EnumType", bound=Enum)


def require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    """Return a string-keyed mapping or raise a contextual error."""

    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ModelValidationError(f"{field_name} must be an object with string keys")
    return value


def require_list(value: Any, field_name: str) -> list[Any]:
    """Return a list or raise a contextual error."""

    if not isinstance(value, list):
        raise ModelValidationError(f"{field_name} must be a list")
    return value


def require_string(value: Any, field_name: str, *, allow_blank: bool = False) -> str:
    """Return a trimmed string with an optional non-blank constraint."""

    if not isinstance(value, str):
        raise ModelValidationError(f"{field_name} must be a string")
    normalized = value.strip()
    if not allow_blank and not normalized:
        raise ModelValidationError(f"{field_name} cannot be blank")
    return normalized


def optional_string(value: Any, field_name: str) -> str | None:
    """Return a trimmed optional string, normalizing blank values to None."""

    if value is None:
        return None
    normalized = require_string(value, field_name, allow_blank=True)
    return normalized or None


def require_bool(value: Any, field_name: str) -> bool:
    """Return an actual bool rather than accepting integers as booleans."""

    if not isinstance(value, bool):
        raise ModelValidationError(f"{field_name} must be true or false")
    return value


def require_int(value: Any, field_name: str, *, minimum: int | None = None) -> int:
    """Return a validated integer with an optional minimum."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise ModelValidationError(f"{field_name} must be at least {minimum}")
    return value


def require_uuid(value: Any, field_name: str) -> str:
    """Return a canonical UUID string."""

    text = require_string(value, field_name)
    try:
        return str(UUID(text))
    except (ValueError, AttributeError) as error:
        raise ModelValidationError(f"{field_name} must be a valid UUID") from error


def require_aware_datetime(value: Any, field_name: str) -> datetime:
    """Return a timezone-aware datetime parsed from an ISO 8601 value."""

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ModelValidationError(f"{field_name} must be an ISO 8601 timestamp") from error
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ModelValidationError(f"{field_name} must be a datetime or ISO 8601 string")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ModelValidationError(f"{field_name} must include a timezone offset")
    return parsed


def optional_aware_datetime(value: Any, field_name: str) -> datetime | None:
    """Return an optional timezone-aware datetime."""

    return None if value is None else require_aware_datetime(value, field_name)


def require_date(value: Any, field_name: str) -> date:
    """Return a date parsed from YYYY-MM-DD without accepting datetimes."""

    if isinstance(value, datetime):
        raise ModelValidationError(f"{field_name} must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ModelValidationError(f"{field_name} must be a YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ModelValidationError(f"{field_name} must be a YYYY-MM-DD date") from error


def optional_date(value: Any, field_name: str) -> date | None:
    """Return an optional date."""

    return None if value is None else require_date(value, field_name)


def require_clock_time(value: Any, field_name: str) -> time:
    """Return an hour/minute local clock value."""

    if isinstance(value, time):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.strptime(value, "%H:%M").time()
        except ValueError as error:
            raise ModelValidationError(f"{field_name} must use HH:MM format") from error
    else:
        raise ModelValidationError(f"{field_name} must be a time or HH:MM string")

    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise ModelValidationError(f"{field_name} must be a local HH:MM clock time")
    return parsed


def optional_clock_time(value: Any, field_name: str) -> time | None:
    """Return an optional hour/minute local clock value."""

    return None if value is None else require_clock_time(value, field_name)


def require_enum(value: Any, enum_type: type[EnumType], field_name: str) -> EnumType:
    """Return a member of the requested enum."""

    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        choices = ", ".join(str(member.value) for member in enum_type)
        raise ModelValidationError(f"{field_name} must be one of: {choices}") from error


def collect_extra(data: dict[str, Any], known_fields: set[str]) -> dict[str, Any]:
    """Copy unknown keys so compatible future fields survive a round trip."""

    return {key: deepcopy(value) for key, value in data.items() if key not in known_fields}


def merge_extra(extra: dict[str, Any], known: dict[str, Any]) -> dict[str, Any]:
    """Merge copied extension data without allowing it to replace known fields."""

    merged = deepcopy(extra)
    merged.update(known)
    return merged


def serialize_datetime(value: datetime | None) -> str | None:
    """Serialize an aware datetime after validating it."""

    if value is None:
        return None
    return require_aware_datetime(value, "timestamp").isoformat()


def serialize_date(value: date | None) -> str | None:
    """Serialize an optional date."""

    return value.isoformat() if value is not None else None


def serialize_clock_time(value: time | None) -> str | None:
    """Serialize an optional local clock time as HH:MM."""

    return value.strftime("%H:%M") if value is not None else None
