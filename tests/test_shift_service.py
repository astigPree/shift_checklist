"""Tests for overnight shift calculation, materialization, and rollover."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from constants import Recurrence, TaskStatus
from models import DailyRecord, DailyRecordsDocument, TaskDocument, TaskTemplate
from services import (
    ShiftService,
    ShiftStateError,
    StorageService,
    TaskService,
    active_shift_date,
    scheduled_datetime,
    shift_end,
    shift_start,
)

MANILA = timezone(timedelta(hours=8))


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


def make_task(title: str, **changes: object) -> TaskTemplate:
    values: dict[str, object] = {
        "title": title,
        "category": "General",
        "created_at": datetime(2026, 8, 1, 20, 0, tzinfo=MANILA),
        "updated_at": datetime(2026, 8, 1, 20, 0, tzinfo=MANILA),
    }
    values.update(changes)
    return TaskTemplate(**values)  # type: ignore[arg-type]


def configured_services(
    tmp_path: Path,
    clock: MutableClock,
    tasks: list[TaskTemplate] | None = None,
) -> tuple[StorageService, ShiftService, TaskService]:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    storage.save_tasks(TaskDocument(tasks=tasks or []))
    shift_service = ShiftService(storage, clock=clock)
    return storage, shift_service, TaskService(storage, shift_service)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (datetime(2026, 8, 1, 11, 59, tzinfo=MANILA), date(2026, 7, 31)),
        (datetime(2026, 8, 1, 12, 0, tzinfo=MANILA), date(2026, 8, 1)),
        (datetime(2026, 8, 1, 23, 59, tzinfo=MANILA), date(2026, 8, 1)),
        (datetime(2026, 8, 2, 4, 0, tzinfo=MANILA), date(2026, 8, 1)),
        (datetime(2026, 8, 2, 8, 0, tzinfo=MANILA), date(2026, 8, 1)),
        (datetime(2026, 8, 2, 12, 0, tzinfo=MANILA), date(2026, 8, 2)),
    ],
)
def test_active_shift_date_uses_noon_boundary(current: datetime, expected: date) -> None:
    assert active_shift_date(current, time(12, 0)) == expected


def test_shift_helpers_map_overnight_scheduled_times() -> None:
    shift_date = date(2026, 8, 1)

    assert shift_start(shift_date, time(12), MANILA) == datetime(
        2026, 8, 1, 12, tzinfo=MANILA
    )
    assert shift_end(shift_date, time(12), MANILA) == datetime(
        2026, 8, 2, 12, tzinfo=MANILA
    )
    assert scheduled_datetime(shift_date, time(20), time(12), MANILA) == datetime(
        2026, 8, 1, 20, tzinfo=MANILA
    )
    assert scheduled_datetime(shift_date, time(4), time(12), MANILA) == datetime(
        2026, 8, 2, 4, tzinfo=MANILA
    )
    assert scheduled_datetime(shift_date, time(8), time(12), MANILA) == datetime(
        2026, 8, 2, 8, tzinfo=MANILA
    )


def test_time_helpers_require_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone offset"):
        active_shift_date(datetime(2026, 8, 1, 20), time(12))


def test_materializes_only_applicable_templates_once(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 2, 4, tzinfo=MANILA))
    tasks = [
        make_task("Daily"),
        make_task(
            "One time now",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 1),
        ),
        make_task(
            "One time later",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 2),
        ),
        make_task("Disabled", enabled=False),
    ]
    _storage, shift_service, _task_service = configured_services(tmp_path, clock, tasks)

    first = shift_service.ensure_current_shift()
    second = shift_service.ensure_current_shift()

    assert first.shift_date == date(2026, 8, 1)
    assert [item.title for item in first.occurrences] == ["Daily", "One time now"]
    assert [item.id for item in second.occurrences] == [
        item.id for item in first.occurrences
    ]


def test_rollover_finalizes_old_shift_and_opens_new_daily_tasks(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 1, 20, tzinfo=MANILA))
    storage, shift_service, task_service = configured_services(
        tmp_path,
        clock,
        [make_task("Complete me"), make_task("Miss me")],
    )
    old_record = shift_service.ensure_current_shift()
    task_service.complete_occurrence(
        old_record.occurrences[0].id,
        completed_at=datetime(2026, 8, 1, 21, tzinfo=MANILA),
    )

    clock.current = datetime(2026, 8, 2, 12, tzinfo=MANILA)
    new_record = shift_service.ensure_current_shift()
    persisted = storage.load_daily_records()
    old_persisted = next(
        record for record in persisted.records if record.shift_date == date(2026, 8, 1)
    )

    assert old_persisted.closed_at == datetime(2026, 8, 2, 12, tzinfo=MANILA)
    assert [item.status for item in old_persisted.occurrences] == [
        TaskStatus.COMPLETED,
        TaskStatus.MISSED,
    ]
    assert new_record.shift_date == date(2026, 8, 2)
    assert all(item.status is TaskStatus.PENDING for item in new_record.occurrences)


def test_startup_after_several_days_does_not_invent_empty_records(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 1, 20, tzinfo=MANILA))
    storage, shift_service, _task_service = configured_services(
        tmp_path, clock, [make_task("Daily")]
    )
    shift_service.ensure_current_shift()

    clock.current = datetime(2026, 8, 6, 3, tzinfo=MANILA)
    current = shift_service.ensure_current_shift()

    records = storage.load_daily_records().records
    assert current.shift_date == date(2026, 8, 5)
    assert [record.shift_date for record in records] == [
        date(2026, 8, 1),
        date(2026, 8, 5),
    ]


def test_next_boundary_recalculates_after_reset_setting_change(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 2, 10, tzinfo=MANILA))
    storage, shift_service, _task_service = configured_services(tmp_path, clock)

    assert shift_service.current_shift_date() == date(2026, 8, 1)
    assert shift_service.next_boundary() == datetime(2026, 8, 2, 12, tzinfo=MANILA)

    settings = storage.load_settings()
    settings.settings.reset_time = time(8)
    storage.save_settings(settings)

    assert shift_service.current_shift_date() == date(2026, 8, 2)
    assert shift_service.next_boundary() == datetime(2026, 8, 3, 8, tzinfo=MANILA)


def test_future_open_shift_is_not_silently_destroyed(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 2, 4, tzinfo=MANILA))
    storage, shift_service, _task_service = configured_services(tmp_path, clock)
    storage.save_daily_records(
        DailyRecordsDocument(
            records=[
                DailyRecord(
                    shift_date=date(2026, 8, 3),
                    opened_at=datetime(2026, 8, 3, 12, tzinfo=MANILA),
                )
            ]
        )
    )

    with pytest.raises(ShiftStateError, match="later than"):
        shift_service.ensure_current_shift()


def test_seconds_until_boundary_is_non_negative(tmp_path: Path) -> None:
    clock = MutableClock(datetime(2026, 8, 2, 11, 59, 30, tzinfo=MANILA))
    _storage, shift_service, _task_service = configured_services(tmp_path, clock)

    assert shift_service.seconds_until_next_boundary() == 30
