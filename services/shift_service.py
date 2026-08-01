"""Active-shift calculation, materialization, synchronization, and rollover."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta, tzinfo

from constants import Recurrence, ShopifyStatus, TaskStatus, TaskType
from models import (
    DailyRecord,
    ModelValidationError,
    ShopifyDetails,
    TaskOccurrence,
    TaskTemplate,
)
from models.validation import require_aware_datetime, require_clock_time, require_date
from services.storage_service import StorageService

Clock = Callable[[], datetime]


class ShiftStateError(RuntimeError):
    """Raised when stored shift state cannot be reconciled safely."""


def _local_now() -> datetime:
    return datetime.now().astimezone()


def active_shift_date(at: datetime, reset_time: time) -> date:
    """Return the calendar date on which the active shift began."""

    current = require_aware_datetime(at, "at")
    reset = require_clock_time(reset_time, "reset_time")
    local_clock = current.timetz().replace(tzinfo=None)
    return current.date() if local_clock >= reset else current.date() - timedelta(days=1)


def shift_start(shift_date: date, reset_time: time, timezone: tzinfo) -> datetime:
    """Return the inclusive start boundary for a shift."""

    validated_date = require_date(shift_date, "shift_date")
    reset = require_clock_time(reset_time, "reset_time")
    return datetime.combine(validated_date, reset, tzinfo=timezone)


def shift_end(shift_date: date, reset_time: time, timezone: tzinfo) -> datetime:
    """Return the exclusive end boundary for a shift."""

    return shift_start(shift_date + timedelta(days=1), reset_time, timezone)


def scheduled_datetime(
    shift_date: date,
    scheduled_time: time,
    reset_time: time,
    timezone: tzinfo,
) -> datetime:
    """Map a local task clock time into its correct overnight shift datetime."""

    validated_date = require_date(shift_date, "shift_date")
    scheduled = require_clock_time(scheduled_time, "scheduled_time")
    reset = require_clock_time(reset_time, "reset_time")
    calendar_date = (
        validated_date if scheduled >= reset else validated_date + timedelta(days=1)
    )
    return datetime.combine(calendar_date, scheduled, tzinfo=timezone)


class ShiftService:
    """Own the invariant that exactly one current daily record is open."""

    def __init__(self, storage: StorageService, *, clock: Clock | None = None) -> None:
        self.storage = storage
        self._clock = clock or _local_now

    def now(self) -> datetime:
        return require_aware_datetime(self._clock(), "clock result")

    def current_shift_date(self, *, at: datetime | None = None) -> date:
        current = at or self.now()
        settings = self.storage.load_settings().settings
        return active_shift_date(current, settings.reset_time)

    def due_at(self, occurrence: TaskOccurrence, *, at: datetime | None = None) -> datetime | None:
        """Return an occurrence's due datetime in the current local timezone."""

        if occurrence.scheduled_time is None:
            return None
        current = at or self.now()
        settings = self.storage.load_settings().settings
        return scheduled_datetime(
            occurrence.shift_date,
            occurrence.scheduled_time,
            settings.reset_time,
            current.tzinfo,
        )

    def next_boundary(self, *, at: datetime | None = None) -> datetime:
        """Return the next shift boundary after the supplied time."""

        current = at or self.now()
        settings = self.storage.load_settings().settings
        current_date = active_shift_date(current, settings.reset_time)
        return shift_end(current_date, settings.reset_time, current.tzinfo)

    def seconds_until_next_boundary(self, *, at: datetime | None = None) -> float:
        current = at or self.now()
        return max(0.0, (self.next_boundary(at=current) - current).total_seconds())

    def ensure_current_shift(self, *, at: datetime | None = None) -> DailyRecord:
        """Finalize an older open shift and return a synchronized current record."""

        current = require_aware_datetime(at or self.now(), "at")
        settings = self.storage.load_settings().settings
        expected_date = active_shift_date(current, settings.reset_time)
        task_document = self.storage.load_tasks()
        records_document = self.storage.load_daily_records()
        open_record = next(
            (record for record in records_document.records if not record.is_closed), None
        )
        changed = False

        if open_record is not None and open_record.shift_date > expected_date:
            raise ShiftStateError(
                "Stored open shift is later than the current calculated shift; "
                "check the Windows clock and reset-time setting"
            )

        if open_record is not None and open_record.shift_date < expected_date:
            self._finalize_record(open_record, settings.reset_time, current.tzinfo)
            open_record = None
            changed = True

        current_record = next(
            (record for record in records_document.records if record.shift_date == expected_date),
            None,
        )
        if current_record is not None and current_record.is_closed:
            raise ShiftStateError(
                f"Shift {expected_date.isoformat()} is already closed and cannot be reopened"
            )

        if open_record is None:
            if current_record is None:
                current_record = DailyRecord(
                    shift_date=expected_date,
                    opened_at=current,
                    occurrences=self._materialize(
                        task_document.tasks, expected_date, created_at=current
                    ),
                )
                records_document.records.append(current_record)
                changed = True
            else:
                open_record = current_record

        current_record = current_record or open_record
        if current_record is None:
            raise ShiftStateError("Could not resolve the current shift record")

        if self._synchronize_record(
            current_record,
            task_document.tasks,
            expected_date,
            synchronized_at=current,
            reset_time=settings.reset_time,
        ):
            changed = True

        if changed:
            self.storage.save_daily_records(records_document)
        return DailyRecord.from_dict(current_record.to_dict())

    def synchronize_current_shift(self, *, at: datetime | None = None) -> DailyRecord:
        """Public idempotent synchronization entry point used after template changes."""

        return self.ensure_current_shift(at=at)

    @staticmethod
    def _is_applicable(template: TaskTemplate, shift_date: date) -> bool:
        if not template.enabled:
            return False
        if template.recurrence is Recurrence.DAILY:
            return True
        return template.target_shift_date == shift_date

    def _materialize(
        self,
        templates: list[TaskTemplate],
        shift_date: date,
        *,
        created_at: datetime,
    ) -> list[TaskOccurrence]:
        return [
            TaskOccurrence.from_template(template, shift_date, created_at=created_at)
            for template in sorted(templates, key=lambda item: (item.sort_order, item.title))
            if self._is_applicable(template, shift_date)
        ]

    def _synchronize_record(
        self,
        record: DailyRecord,
        templates: list[TaskTemplate],
        shift_date: date,
        *,
        synchronized_at: datetime,
        reset_time: time,
    ) -> bool:
        applicable = {
            template.id: template
            for template in templates
            if self._is_applicable(template, shift_date)
        }
        changed = False
        synchronized: list[TaskOccurrence] = []
        seen_template_ids: set[str] = set()

        for occurrence in record.occurrences:
            template = applicable.get(occurrence.template_id)
            if template is None:
                if occurrence.status is TaskStatus.COMPLETED:
                    synchronized.append(occurrence)
                else:
                    changed = True
                continue
            seen_template_ids.add(template.id)
            updated = self._snapshot_with_template(
                occurrence,
                template,
                synchronized_at=synchronized_at,
                reset_time=reset_time,
            )
            synchronized.append(updated)
            if updated.to_dict() != occurrence.to_dict():
                changed = True

        for template_id, template in applicable.items():
            if template_id not in seen_template_ids:
                synchronized.append(
                    TaskOccurrence.from_template(
                        template, shift_date, created_at=synchronized_at
                    )
                )
                changed = True

        synchronized.sort(key=lambda item: (item.sort_order, item.title, item.id))
        if [item.id for item in synchronized] != [item.id for item in record.occurrences]:
            changed = True
        if changed:
            record.occurrences = synchronized
        return changed

    @staticmethod
    def _snapshot_with_template(
        occurrence: TaskOccurrence,
        template: TaskTemplate,
        *,
        synchronized_at: datetime,
        reset_time: time,
    ) -> TaskOccurrence:
        shopify_details = (
            ShopifyDetails.from_dict(template.shopify_details.to_dict())
            if template.shopify_details
            else None
        )
        status = occurrence.status
        completed_at = occurrence.completed_at
        if template.task_type is TaskType.SHOPIFY and shopify_details is not None:
            if shopify_details.status is ShopifyStatus.COMPLETED:
                status = TaskStatus.COMPLETED
                completed_at = shopify_details.completed_at
            elif status is TaskStatus.COMPLETED:
                status = TaskStatus.PENDING
                completed_at = None
        pre_due_fired = occurrence.pre_due_reminder_fired
        due_fired = occurrence.due_reminder_fired
        reminder_changed = (
            occurrence.reminder_enabled != template.reminder_enabled
            or occurrence.scheduled_time != template.scheduled_time
            or occurrence.reminder_lead_minutes != template.reminder_lead_minutes
        )
        if reminder_changed and template.reminder_enabled and template.scheduled_time:
            new_due = scheduled_datetime(
                occurrence.shift_date,
                template.scheduled_time,
                reset_time,
                synchronized_at.tzinfo,
            )
            new_pre_due = new_due - timedelta(minutes=template.reminder_lead_minutes)
            if new_due > synchronized_at:
                due_fired = False
            if new_pre_due > synchronized_at:
                pre_due_fired = False
        return TaskOccurrence(
            id=occurrence.id,
            template_id=template.id,
            shift_date=occurrence.shift_date,
            title=template.title,
            category=template.category,
            notes=template.notes,
            scheduled_time=template.scheduled_time,
            reminder_enabled=template.reminder_enabled,
            reminder_lead_minutes=template.reminder_lead_minutes,
            sort_order=template.sort_order,
            task_type=template.task_type,
            shopify_details=shopify_details,
            status=status,
            completed_at=completed_at,
            pre_due_reminder_fired=pre_due_fired,
            due_reminder_fired=due_fired,
            created_at=occurrence.created_at,
            extra=occurrence.extra,
        )

    @staticmethod
    def _finalize_record(record: DailyRecord, reset_time: time, timezone: tzinfo) -> None:
        if record.is_closed:
            raise ModelValidationError("cannot finalize an already closed daily record")
        for occurrence in record.occurrences:
            if occurrence.status is TaskStatus.PENDING:
                occurrence.status = TaskStatus.MISSED
        record.closed_at = shift_end(record.shift_date, reset_time, timezone)
