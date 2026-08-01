"""Task and client-message reminder evaluation with notification fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from constants import APP_NAME, TaskStatus
from models import TaskOccurrence
from models.validation import require_aware_datetime
from services.message_check_service import MessageCheckService
from services.shift_service import ShiftService, scheduled_datetime
from services.storage_service import StorageService

LOGGER = logging.getLogger(__name__)


class ReminderKind(StrEnum):
    TASK_UPCOMING = "task_upcoming"
    TASK_DUE = "task_due"
    CLIENT_MESSAGES = "client_messages"


@dataclass(frozen=True, slots=True)
class ReminderEvent:
    """A single deduplicated reminder delivered to desktop and/or in-app UI."""

    kind: ReminderKind
    title: str
    message: str
    due_at: datetime
    occurrence_id: str | None = None


class NotificationBackend(Protocol):
    def notify(self, title: str, message: str) -> None: ...


class SoundBackend(Protocol):
    def play(self, path: Path) -> None: ...


class PlyerNotificationBackend:
    """Thin adapter around Plyer's platform notification facade."""

    def notify(self, title: str, message: str) -> None:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name=APP_NAME,
            timeout=10,
        )


class KivySoundBackend:
    """Load and play a configured sound without retaining UI state."""

    def play(self, path: Path) -> None:
        from kivy.core.audio import SoundLoader

        sound = SoundLoader.load(str(path))
        if sound is None:
            raise RuntimeError(f"No sound provider could load {path}")
        sound.play()


BannerCallback = Callable[[ReminderEvent], None]


class ReminderService:
    """Poll reminder boundaries and persist task deduplication flags."""

    def __init__(
        self,
        storage: StorageService,
        shift_service: ShiftService,
        message_check_service: MessageCheckService,
        *,
        notification_backend: NotificationBackend | None = None,
        sound_backend: SoundBackend | None = None,
    ) -> None:
        self.storage = storage
        self.shift_service = shift_service
        self.message_check_service = message_check_service
        self.notification_backend = notification_backend or PlyerNotificationBackend()
        self.sound_backend = sound_backend or KivySoundBackend()
        self._banner_callbacks: list[BannerCallback] = []
        self._client_reminder_keys_fired: set[str] = set()
        self.last_errors: list[str] = []

    def subscribe_banner(self, callback: BannerCallback) -> None:
        if callback not in self._banner_callbacks:
            self._banner_callbacks.append(callback)

    def unsubscribe_banner(self, callback: BannerCallback) -> None:
        if callback in self._banner_callbacks:
            self._banner_callbacks.remove(callback)

    def poll(self, *, at: datetime | None = None) -> list[ReminderEvent]:
        """Evaluate all reminders once and return newly fired events."""

        current = require_aware_datetime(at or self.shift_service.now(), "at")
        current_shift = self.shift_service.ensure_current_shift(at=current)
        settings = self.storage.load_settings().settings
        records_document = self.storage.load_daily_records()
        record = next(
            (
                item
                for item in records_document.records
                if item.shift_date == current_shift.shift_date and not item.is_closed
            ),
            None,
        )
        events: list[ReminderEvent] = []
        task_flags_changed = False

        if record is not None:
            for occurrence in record.occurrences:
                event, changed = self._evaluate_occurrence(
                    occurrence,
                    current=current,
                    reset_time=settings.reset_time,
                )
                task_flags_changed = task_flags_changed or changed
                if event is not None:
                    events.append(event)

        if task_flags_changed:
            self.storage.save_daily_records(records_document)

        client_due_at = self.message_check_service.next_reminder(at=current)
        client_key = self.message_check_service.reminder_key(at=current)
        if current >= client_due_at and client_key not in self._client_reminder_keys_fired:
            self._client_reminder_keys_fired.add(client_key)
            events.append(
                ReminderEvent(
                    ReminderKind.CLIENT_MESSAGES,
                    "Check client messages",
                    "It is time to review client messages and record the check.",
                    client_due_at,
                )
            )

        for event in events:
            self._dispatch(event, settings=settings)
        return events

    @staticmethod
    def _evaluate_occurrence(
        occurrence: TaskOccurrence,
        *,
        current: datetime,
        reset_time: time,
    ) -> tuple[ReminderEvent | None, bool]:
        if (
            occurrence.status is not TaskStatus.PENDING
            or not occurrence.reminder_enabled
            or occurrence.scheduled_time is None
        ):
            return None, False

        due_at = scheduled_datetime(
            occurrence.shift_date,
            occurrence.scheduled_time,
            reset_time,
            current.tzinfo,
        )
        pre_due_at = due_at - timedelta(minutes=occurrence.reminder_lead_minutes)

        if current >= due_at:
            if occurrence.due_reminder_fired:
                return None, False
            occurrence.pre_due_reminder_fired = True
            occurrence.due_reminder_fired = True
            overdue = current > due_at
            message = (
                f"Overdue: {occurrence.title}"
                if overdue
                else f"Due now: {occurrence.title}"
            )
            return (
                ReminderEvent(
                    ReminderKind.TASK_DUE,
                    "Shift task overdue" if overdue else "Shift task due",
                    message,
                    due_at,
                    occurrence.id,
                ),
                True,
            )

        if (
            occurrence.reminder_lead_minutes > 0
            and current >= pre_due_at
            and not occurrence.pre_due_reminder_fired
        ):
            occurrence.pre_due_reminder_fired = True
            return (
                ReminderEvent(
                    ReminderKind.TASK_UPCOMING,
                    "Upcoming shift task",
                    f"{occurrence.title} is due at {due_at.strftime('%I:%M %p').lstrip('0')}.",
                    due_at,
                    occurrence.id,
                ),
                True,
            )
        return None, False

    def _dispatch(self, event: ReminderEvent, *, settings: object) -> None:
        notifications_enabled = bool(getattr(settings, "notifications_enabled"))
        sound_enabled = bool(getattr(settings, "sound_enabled"))
        sound_path = getattr(settings, "reminder_sound_path")

        if notifications_enabled:
            try:
                self.notification_backend.notify(event.title, event.message)
            except Exception as error:  # platform adapters raise backend-specific errors
                message = f"Desktop notification failed: {error}"
                self.last_errors.append(message)
                LOGGER.warning(message)

        if sound_enabled and sound_path:
            try:
                self.sound_backend.play(Path(sound_path))
            except Exception as error:  # sound providers vary by Windows installation
                message = f"Reminder sound failed: {error}"
                self.last_errors.append(message)
                LOGGER.warning(message)

        for callback in tuple(self._banner_callbacks):
            try:
                callback(event)
            except Exception as error:  # a broken view must not stop reminder persistence
                message = f"In-app reminder callback failed: {error}"
                self.last_errors.append(message)
                LOGGER.warning(message)
