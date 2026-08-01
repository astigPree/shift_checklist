"""Tests for message-check timing and reminder delivery/deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from constants import LiveTaskState, TaskStatus
from models import TaskDocument, TaskTemplate
from services import (
    MessageCheckService,
    ReminderKind,
    ReminderService,
    ShiftService,
    StorageService,
    TaskService,
)

MANILA = timezone(timedelta(hours=8))


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


class FakeNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.calls.append((title, message))
        if self.fail:
            raise RuntimeError("notification unavailable")


class FakeSound:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.paths: list[Path] = []

    def play(self, path: Path) -> None:
        self.paths.append(path)
        if self.fail:
            raise RuntimeError("sound unavailable")


def make_context(
    tmp_path: Path,
    *,
    current: datetime,
    tasks: list[TaskTemplate] | None = None,
) -> tuple[StorageService, MutableClock, ShiftService, TaskService, MessageCheckService]:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    storage.save_tasks(TaskDocument(tasks=tasks or []))
    clock = MutableClock(current)
    shift_service = ShiftService(storage, clock=clock)
    task_service = TaskService(storage, shift_service)
    message_service = MessageCheckService(
        storage,
        shift_service,
        application_started_at=current,
    )
    shift_service.ensure_current_shift()
    return storage, clock, shift_service, task_service, message_service


def make_reminder_task() -> TaskTemplate:
    created = datetime(2026, 8, 1, 20, tzinfo=MANILA)
    return TaskTemplate(
        title="Check out from JDK",
        category="FastDTR",
        scheduled_time=time(4),
        reminder_enabled=True,
        reminder_lead_minutes=5,
        created_at=created,
        updated_at=created,
    )


def test_message_check_records_event_and_calculates_next_time(tmp_path: Path) -> None:
    checked_at = datetime(2026, 8, 2, 3, 30, tzinfo=MANILA)
    _storage, _clock, _shift, _tasks, messages = make_context(
        tmp_path, current=checked_at
    )

    event = messages.record_check("No new messages", checked_at=checked_at)

    assert event.shift_date == date(2026, 8, 1)
    assert event.next_check_at == datetime(2026, 8, 2, 4, tzinfo=MANILA)
    assert messages.latest_for_shift().id == event.id  # type: ignore[union-attr]
    assert messages.latest_global().note == "No new messages"  # type: ignore[union-attr]
    assert messages.next_reminder(at=checked_at) == event.next_check_at


def test_first_message_reminder_uses_later_of_shift_or_application_start(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 2, 3, 30, tzinfo=MANILA)
    _storage, _clock, _shift, _tasks, messages = make_context(
        tmp_path, current=started
    )

    assert messages.next_reminder(at=started) == datetime(
        2026, 8, 2, 4, tzinfo=MANILA
    )


def test_task_pre_due_and_due_fire_once_and_survive_service_restart(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 2, 3, 54, tzinfo=MANILA)
    storage, clock, shift, _tasks, messages = make_context(
        tmp_path,
        current=started,
        tasks=[make_reminder_task()],
    )
    notifier = FakeNotifier()
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=notifier,
        sound_backend=FakeSound(),
    )

    assert reminder.poll() == []
    clock.current = datetime(2026, 8, 2, 3, 55, tzinfo=MANILA)
    upcoming = reminder.poll()
    assert [event.kind for event in upcoming] == [ReminderKind.TASK_UPCOMING]
    assert reminder.poll() == []

    clock.current = datetime(2026, 8, 2, 4, tzinfo=MANILA)
    due = reminder.poll()
    assert [event.kind for event in due] == [ReminderKind.TASK_DUE]
    assert reminder.poll() == []

    restarted = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )
    assert restarted.poll() == []
    assert len(notifier.calls) == 2


def test_late_startup_sends_only_one_overdue_task_event(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 4, 10, tzinfo=MANILA)
    storage, _clock, shift, _tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )

    events = reminder.poll()

    assert [event.kind for event in events] == [ReminderKind.TASK_DUE]
    occurrence = storage.load_daily_records().records[0].occurrences[0]
    assert occurrence.pre_due_reminder_fired is True
    assert occurrence.due_reminder_fired is True


def test_completed_task_suppresses_future_reminder(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 3, 54, tzinfo=MANILA)
    storage, clock, shift, tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    occurrence = shift.ensure_current_shift().occurrences[0]
    tasks.complete_occurrence(occurrence.id, completed_at=current)
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )

    clock.current = datetime(2026, 8, 2, 4, tzinfo=MANILA)

    assert reminder.poll() == []
    assert tasks.live_state(occurrence, at=clock.current) is not LiveTaskState.COMPLETED
    persisted = shift.ensure_current_shift().occurrences[0]
    assert tasks.live_state(persisted, at=clock.current) is LiveTaskState.COMPLETED


def test_editing_reminder_into_future_resets_fired_flags(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 4, 1, tzinfo=MANILA)
    storage, clock, shift, tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )
    reminder.poll()
    template = storage.load_tasks().tasks[0]

    tasks.update_task(template.id, scheduled_time=time(5))
    updated = shift.ensure_current_shift().occurrences[0]

    assert updated.pre_due_reminder_fired is False
    assert updated.due_reminder_fired is False
    clock.current = datetime(2026, 8, 2, 4, 55, tzinfo=MANILA)
    events = reminder.poll()
    assert [event.kind for event in events if event.occurrence_id] == [
        ReminderKind.TASK_UPCOMING
    ]


def test_failed_desktop_notification_still_uses_banner_and_deduplicates(
    tmp_path: Path,
) -> None:
    current = datetime(2026, 8, 2, 4, tzinfo=MANILA)
    storage, _clock, shift, _tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    notifier = FakeNotifier(fail=True)
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=notifier,
        sound_backend=FakeSound(),
    )
    banner_events = []
    reminder.subscribe_banner(banner_events.append)

    first = reminder.poll()
    second = reminder.poll()

    assert len(first) == 1
    assert second == []
    assert banner_events == first
    assert any("Desktop notification failed" in error for error in reminder.last_errors)


def test_missing_sound_is_non_fatal(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 4, tzinfo=MANILA)
    storage, _clock, shift, _tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    settings = storage.load_settings()
    settings.settings.reminder_sound_path = "missing.wav"
    storage.save_settings(settings)
    sound = FakeSound(fail=True)
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=sound,
    )

    assert reminder.poll()
    assert sound.paths == [Path("missing.wav")]
    assert any("Reminder sound failed" in error for error in reminder.last_errors)


def test_client_message_reminder_fires_once_until_a_new_check(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 3, 30, tzinfo=MANILA)
    storage, clock, shift, _tasks, messages = make_context(tmp_path, current=current)
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )

    clock.current = datetime(2026, 8, 2, 4, tzinfo=MANILA)
    assert [event.kind for event in reminder.poll()] == [ReminderKind.CLIENT_MESSAGES]
    assert reminder.poll() == []

    messages.record_check(checked_at=clock.current)
    clock.current = datetime(2026, 8, 2, 4, 30, tzinfo=MANILA)
    assert [event.kind for event in reminder.poll()] == [ReminderKind.CLIENT_MESSAGES]


def test_reminder_flags_are_persisted_only_on_pending_tasks(tmp_path: Path) -> None:
    current = datetime(2026, 8, 2, 4, tzinfo=MANILA)
    storage, _clock, shift, tasks, messages = make_context(
        tmp_path,
        current=current,
        tasks=[make_reminder_task()],
    )
    occurrence = shift.ensure_current_shift().occurrences[0]
    tasks.complete_occurrence(occurrence.id, completed_at=current)
    reminder = ReminderService(
        storage,
        shift,
        messages,
        notification_backend=FakeNotifier(),
        sound_backend=FakeSound(),
    )

    reminder.poll()

    persisted = storage.load_daily_records().records[0].occurrences[0]
    assert persisted.status is TaskStatus.COMPLETED
    assert persisted.due_reminder_fired is False
