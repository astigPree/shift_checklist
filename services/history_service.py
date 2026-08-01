"""Read-only historical shift queries and summary calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from constants import TaskStatus, TaskType
from models import DailyRecord, MessageCheck, TaskOccurrence
from models.validation import require_date
from services.storage_service import StorageService


class HistoryNotFoundError(LookupError):
    """Raised when a requested shift record does not exist."""


@dataclass(frozen=True, slots=True)
class DailySummary:
    """Aggregate counts for one active or historical shift."""

    shift_date: date
    is_closed: bool
    total: int
    completed: int
    missed: int
    pending: int
    attendance_completed: int
    shopify_total: int
    shopify_completed: int
    message_checks: int


@dataclass(frozen=True, slots=True)
class ShiftHistoryDetail:
    """Independent snapshots for a history detail view."""

    record: DailyRecord
    message_checks: tuple[MessageCheck, ...]


class HistoryService:
    """Expose immutable copies of daily records and related message events."""

    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    def list_summaries(self, *, include_open: bool = False) -> list[DailySummary]:
        records = self.storage.load_daily_records().records
        if not include_open:
            records = [record for record in records if record.is_closed]
        return [
            self._summarize(record)
            for record in sorted(records, key=lambda item: item.shift_date, reverse=True)
        ]

    def get_shift_detail(self, shift_date: date) -> ShiftHistoryDetail:
        target_date = require_date(shift_date, "shift_date")
        record = next(
            (
                item
                for item in self.storage.load_daily_records().records
                if item.shift_date == target_date
            ),
            None,
        )
        if record is None:
            raise HistoryNotFoundError(
                f"shift history not found: {target_date.isoformat()}"
            )
        checks = [
            MessageCheck.from_dict(check.to_dict())
            for check in self.storage.load_message_checks().checks
            if check.shift_date == target_date
        ]
        checks.sort(key=lambda check: check.checked_at)
        return ShiftHistoryDetail(
            DailyRecord.from_dict(record.to_dict()),
            tuple(checks),
        )

    def completed_tasks(self, shift_date: date) -> tuple[TaskOccurrence, ...]:
        return self._tasks_with_status(shift_date, TaskStatus.COMPLETED)

    def missed_tasks(self, shift_date: date) -> tuple[TaskOccurrence, ...]:
        return self._tasks_with_status(shift_date, TaskStatus.MISSED)

    def _tasks_with_status(
        self, shift_date: date, status: TaskStatus
    ) -> tuple[TaskOccurrence, ...]:
        detail = self.get_shift_detail(shift_date)
        return tuple(
            TaskOccurrence.from_dict(occurrence.to_dict())
            for occurrence in detail.record.occurrences
            if occurrence.status is status
        )

    def _summarize(self, record: DailyRecord) -> DailySummary:
        occurrences = record.occurrences
        completed = sum(item.status is TaskStatus.COMPLETED for item in occurrences)
        missed = sum(item.status is TaskStatus.MISSED for item in occurrences)
        pending = sum(item.status is TaskStatus.PENDING for item in occurrences)
        attendance_completed = sum(
            item.category == "FastDTR" and item.status is TaskStatus.COMPLETED
            for item in occurrences
        )
        shopify = [item for item in occurrences if item.task_type is TaskType.SHOPIFY]
        shopify_completed = sum(item.status is TaskStatus.COMPLETED for item in shopify)
        message_count = sum(
            check.shift_date == record.shift_date
            for check in self.storage.load_message_checks().checks
        )
        return DailySummary(
            shift_date=record.shift_date,
            is_closed=record.is_closed,
            total=len(occurrences),
            completed=completed,
            missed=missed,
            pending=pending,
            attendance_completed=attendance_completed,
            shopify_total=len(shopify),
            shopify_completed=shopify_completed,
            message_checks=message_count,
        )
