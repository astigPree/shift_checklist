"""Per-shift checklist records and versioned history document."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from constants import SCHEMA_VERSION
from models.task import TaskOccurrence
from models.validation import (
    ModelValidationError,
    collect_extra,
    merge_extra,
    optional_aware_datetime,
    require_aware_datetime,
    require_date,
    require_int,
    require_list,
    require_mapping,
    serialize_date,
    serialize_datetime,
)


@dataclass(slots=True)
class DailyRecord:
    """All task occurrence snapshots for one active or closed shift."""

    shift_date: date
    opened_at: datetime
    occurrences: list[TaskOccurrence] = field(default_factory=list)
    closed_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.shift_date = require_date(self.shift_date, "daily_record.shift_date")
        self.opened_at = require_aware_datetime(self.opened_at, "daily_record.opened_at")
        self.closed_at = optional_aware_datetime(self.closed_at, "daily_record.closed_at")
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ModelValidationError(
                "daily_record.closed_at cannot be before daily_record.opened_at"
            )
        if not isinstance(self.occurrences, list) or not all(
            isinstance(item, TaskOccurrence) for item in self.occurrences
        ):
            raise ModelValidationError(
                "daily_record.occurrences must contain TaskOccurrence values"
            )
        occurrence_ids = [item.id for item in self.occurrences]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ModelValidationError("daily_record contains duplicate occurrence IDs")
        if any(item.shift_date != self.shift_date for item in self.occurrences):
            raise ModelValidationError(
                "daily_record occurrences must have the same shift_date as their record"
            )

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "shift_date": serialize_date(self.shift_date),
                "opened_at": serialize_datetime(self.opened_at),
                "closed_at": serialize_datetime(self.closed_at),
                "occurrences": [item.to_dict() for item in self.occurrences],
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> DailyRecord:
        data = require_mapping(value, "daily_record")
        occurrences = require_list(data.get("occurrences", []), "daily_record.occurrences")
        return cls(
            shift_date=require_date(data.get("shift_date"), "daily_record.shift_date"),
            opened_at=require_aware_datetime(
                data.get("opened_at"), "daily_record.opened_at"
            ),
            closed_at=optional_aware_datetime(
                data.get("closed_at"), "daily_record.closed_at"
            ),
            occurrences=[TaskOccurrence.from_dict(item) for item in occurrences],
            extra=collect_extra(
                data, {"shift_date", "opened_at", "closed_at", "occurrences"}
            ),
        )


@dataclass(slots=True)
class DailyRecordsDocument:
    """Versioned root document stored in daily_records.json."""

    records: list[DailyRecord] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.schema_version = require_int(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(
                f"daily records schema must be version {SCHEMA_VERSION} after migration"
            )
        if not isinstance(self.records, list) or not all(
            isinstance(record, DailyRecord) for record in self.records
        ):
            raise ModelValidationError("records must contain DailyRecord values")
        shift_dates = [record.shift_date for record in self.records]
        if len(shift_dates) != len(set(shift_dates)):
            raise ModelValidationError("records contains duplicate shift dates")
        open_records = [record for record in self.records if not record.is_closed]
        if len(open_records) > 1:
            raise ModelValidationError("only one daily record may be open")

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "schema_version": self.schema_version,
                "records": [record.to_dict() for record in self.records],
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> DailyRecordsDocument:
        data = require_mapping(value, "daily records document")
        records = require_list(data.get("records", []), "records")
        return cls(
            schema_version=require_int(data.get("schema_version"), "schema_version", minimum=1),
            records=[DailyRecord.from_dict(item) for item in records],
            extra=collect_extra(data, {"schema_version", "records"}),
        )
