"""Manual client-message check events and next-reminder calculation."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from models import MessageCheck
from models.validation import require_aware_datetime, require_string
from services.shift_service import ShiftService, shift_start
from services.storage_service import StorageService


class MessageCheckService:
    """Append immutable message-check events and expose current reminder state."""

    def __init__(
        self,
        storage: StorageService,
        shift_service: ShiftService,
        *,
        application_started_at: datetime | None = None,
    ) -> None:
        self.storage = storage
        self.shift_service = shift_service
        self.application_started_at = require_aware_datetime(
            application_started_at or shift_service.now(), "application_started_at"
        )

    def record_check(
        self,
        note: str = "",
        *,
        checked_at: datetime | None = None,
    ) -> MessageCheck:
        """Append a check event and calculate its next reminder from settings."""

        timestamp = require_aware_datetime(
            checked_at or self.shift_service.now(), "checked_at"
        )
        normalized_note = require_string(note, "note", allow_blank=True)
        current_record = self.shift_service.ensure_current_shift(at=timestamp)
        interval = self.storage.load_settings().settings.client_check_interval_minutes
        event = MessageCheck(
            shift_date=current_record.shift_date,
            checked_at=timestamp,
            next_check_at=timestamp + timedelta(minutes=interval),
            note=normalized_note,
        )
        document = self.storage.load_message_checks()
        document.checks.append(event)
        self.storage.save_message_checks(document)
        return MessageCheck.from_dict(event.to_dict())

    def latest_for_shift(self, shift_date: date | None = None) -> MessageCheck | None:
        """Return the latest event for a shift, defaulting to the active shift."""

        target_date = shift_date or self.shift_service.current_shift_date()
        matching = [
            check
            for check in self.storage.load_message_checks().checks
            if check.shift_date == target_date
        ]
        if not matching:
            return None
        return MessageCheck.from_dict(max(matching, key=lambda item: item.checked_at).to_dict())

    def latest_global(self) -> MessageCheck | None:
        """Return the latest event across all shifts."""

        checks = self.storage.load_message_checks().checks
        if not checks:
            return None
        return MessageCheck.from_dict(max(checks, key=lambda item: item.checked_at).to_dict())

    def next_reminder(self, *, at: datetime | None = None) -> datetime:
        """Return the next active-shift reminder, including the no-check case."""

        current = require_aware_datetime(at or self.shift_service.now(), "at")
        settings = self.storage.load_settings().settings
        shift_date = self.shift_service.current_shift_date(at=current)
        latest = self.latest_for_shift(shift_date)
        if latest is not None:
            return latest.next_check_at

        boundary = shift_start(shift_date, settings.reset_time, current.tzinfo)
        reminder_base = max(boundary, self.application_started_at)
        return reminder_base + timedelta(minutes=settings.client_check_interval_minutes)

    def reminder_key(self, *, at: datetime | None = None) -> str:
        """Return a stable in-session deduplication key for the next reminder."""

        current = require_aware_datetime(at or self.shift_service.now(), "at")
        shift_date = self.shift_service.current_shift_date(at=current)
        latest = self.latest_for_shift(shift_date)
        source = latest.id if latest is not None else "initial"
        return f"{shift_date.isoformat()}:{source}:{self.next_reminder(at=current).isoformat()}"
