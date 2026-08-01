"""Client-message check events and their versioned root document."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from constants import SCHEMA_VERSION
from models.validation import (
    ModelValidationError,
    collect_extra,
    merge_extra,
    require_aware_datetime,
    require_date,
    require_int,
    require_list,
    require_mapping,
    require_string,
    require_uuid,
    serialize_date,
    serialize_datetime,
)


@dataclass(slots=True)
class MessageCheck:
    """Immutable record of one manual client-message check action."""

    shift_date: date
    checked_at: datetime
    next_check_at: datetime
    id: str = field(default_factory=lambda: str(uuid4()))
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.id = require_uuid(self.id, "message_check.id")
        self.shift_date = require_date(self.shift_date, "message_check.shift_date")
        self.checked_at = require_aware_datetime(
            self.checked_at, "message_check.checked_at"
        )
        self.next_check_at = require_aware_datetime(
            self.next_check_at, "message_check.next_check_at"
        )
        self.note = require_string(self.note, "message_check.note", allow_blank=True)
        if self.next_check_at <= self.checked_at:
            raise ModelValidationError(
                "message_check.next_check_at must be after message_check.checked_at"
            )

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "id": self.id,
                "shift_date": serialize_date(self.shift_date),
                "checked_at": serialize_datetime(self.checked_at),
                "next_check_at": serialize_datetime(self.next_check_at),
                "note": self.note,
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> MessageCheck:
        data = require_mapping(value, "message_check")
        return cls(
            id=require_uuid(data.get("id"), "message_check.id"),
            shift_date=require_date(data.get("shift_date"), "message_check.shift_date"),
            checked_at=require_aware_datetime(
                data.get("checked_at"), "message_check.checked_at"
            ),
            next_check_at=require_aware_datetime(
                data.get("next_check_at"), "message_check.next_check_at"
            ),
            note=require_string(
                data.get("note", ""), "message_check.note", allow_blank=True
            ),
            extra=collect_extra(
                data, {"id", "shift_date", "checked_at", "next_check_at", "note"}
            ),
        )


@dataclass(slots=True)
class MessageChecksDocument:
    """Versioned root document stored in message_checks.json."""

    checks: list[MessageCheck] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.schema_version = require_int(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(
                f"message checks schema must be version {SCHEMA_VERSION} after migration"
            )
        if not isinstance(self.checks, list) or not all(
            isinstance(check, MessageCheck) for check in self.checks
        ):
            raise ModelValidationError("checks must contain MessageCheck values")
        identifiers = [check.id for check in self.checks]
        if len(identifiers) != len(set(identifiers)):
            raise ModelValidationError("checks contains duplicate message check IDs")

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "schema_version": self.schema_version,
                "checks": [check.to_dict() for check in self.checks],
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> MessageChecksDocument:
        data = require_mapping(value, "message checks document")
        checks = require_list(data.get("checks", []), "checks")
        return cls(
            schema_version=require_int(data.get("schema_version"), "schema_version", minimum=1),
            checks=[MessageCheck.from_dict(item) for item in checks],
            extra=collect_extra(data, {"schema_version", "checks"}),
        )
