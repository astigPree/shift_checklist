"""Tests for first-launch defaults and read-only historical reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from constants import Recurrence, ShopifyStatus, TaskStatus, TaskType
from models import MessageCheck, MessageChecksDocument, ShopifyDetails, TaskDocument, TaskTemplate
from services import (
    HistoryNotFoundError,
    HistoryService,
    ShiftService,
    StorageService,
    TaskService,
    create_default_tasks,
    seed_default_tasks,
)

MANILA = timezone(timedelta(hours=8))
START = datetime(2026, 8, 1, 20, tzinfo=MANILA)


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


def make_task(title: str, category: str = "General", **changes: object) -> TaskTemplate:
    values: dict[str, object] = {
        "title": title,
        "category": category,
        "created_at": START,
        "updated_at": START,
    }
    values.update(changes)
    return TaskTemplate(**values)  # type: ignore[arg-type]


def test_default_tasks_cover_shift_actions_without_mandatory_shopify_work() -> None:
    tasks = create_default_tasks(created_at=START)
    by_title = {task.title: task for task in tasks}

    assert len(tasks) == 14
    assert by_title["Open FastDTR for JDK checkout"].scheduled_time == time(3, 55)
    assert by_title["Check out from JDK"].scheduled_time == time(4)
    assert by_title["Check in for Happy BUM"].scheduled_time == time(4)
    assert by_title["Open FastDTR for Happy BUM checkout"].scheduled_time == time(7, 55)
    assert by_title["Check out from Happy BUM"].scheduled_time == time(8)
    assert "Check for Shopify update requests" in by_title
    assert not any("Complete requested Shopify" in task.title for task in tasks)
    assert [task.sort_order for task in tasks] == list(range(len(tasks)))


def test_seed_defaults_runs_once_and_does_not_repopulate_deleted_tasks(tmp_path: Path) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()

    assert seed_default_tasks(storage, created_at=START) is True
    assert len(storage.load_tasks().tasks) == 14

    storage.save_tasks(TaskDocument(tasks=[]))

    assert seed_default_tasks(storage, created_at=START) is False
    assert storage.load_tasks().tasks == []


def test_existing_custom_task_is_not_mixed_with_first_launch_defaults(tmp_path: Path) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.save_tasks(TaskDocument(tasks=[make_task("My custom task")]))

    assert seed_default_tasks(storage, created_at=START) is False
    assert [task.title for task in storage.load_tasks().tasks] == ["My custom task"]
    assert storage.should_seed_default_tasks() is False


def test_history_summarizes_closed_shift_and_returns_independent_detail(
    tmp_path: Path,
) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    clock = MutableClock(START)
    shift_service = ShiftService(storage, clock=clock)
    task_service = TaskService(storage, shift_service)
    history_service = HistoryService(storage)
    shift_service.ensure_current_shift()

    fastdtr = task_service.add_task(make_task("Attendance", "FastDTR"))
    pending = task_service.add_task(make_task("Leave unfinished"))
    shopify = task_service.add_task(
        make_task(
            "Update store",
            "Shopify",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 1),
            task_type=TaskType.SHOPIFY,
            shopify_details=ShopifyDetails(
                store_name="Example",
                description="Update navigation",
                requested_at=START,
            ),
        )
    )
    occurrences = {
        item.template_id: item for item in shift_service.ensure_current_shift().occurrences
    }
    task_service.complete_occurrence(
        occurrences[fastdtr.id].id,
        completed_at=START + timedelta(hours=1),
    )
    task_service.set_shopify_status(
        occurrences[shopify.id].id,
        ShopifyStatus.COMPLETED,
        changed_at=START + timedelta(hours=2),
    )
    storage.save_message_checks(
        MessageChecksDocument(
            checks=[
                MessageCheck(
                    shift_date=date(2026, 8, 1),
                    checked_at=START + timedelta(hours=3),
                    next_check_at=START + timedelta(hours=3, minutes=30),
                    note="Reviewed",
                )
            ]
        )
    )

    clock.current = datetime(2026, 8, 2, 12, tzinfo=MANILA)
    shift_service.ensure_current_shift()
    summaries = history_service.list_summaries()
    detail = history_service.get_shift_detail(date(2026, 8, 1))

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.total == 3
    assert summary.completed == 2
    assert summary.missed == 1
    assert summary.pending == 0
    assert summary.attendance_completed == 1
    assert summary.shopify_total == 1
    assert summary.shopify_completed == 1
    assert summary.message_checks == 1
    assert detail.message_checks[0].note == "Reviewed"
    assert [item.title for item in history_service.completed_tasks(date(2026, 8, 1))] == [
        "Attendance",
        "Update store",
    ]
    assert [item.template_id for item in history_service.missed_tasks(date(2026, 8, 1))] == [
        pending.id
    ]

    detail.record.occurrences[0].title = "Mutated copy"
    reloaded = history_service.get_shift_detail(date(2026, 8, 1))
    assert all(item.title != "Mutated copy" for item in reloaded.record.occurrences)


def test_history_excludes_open_shift_by_default_and_sorts_newest_first(
    tmp_path: Path,
) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    storage.save_tasks(TaskDocument(tasks=[make_task("Daily")]))
    clock = MutableClock(START)
    shift_service = ShiftService(storage, clock=clock)
    history_service = HistoryService(storage)
    shift_service.ensure_current_shift()

    clock.current = datetime(2026, 8, 2, 12, tzinfo=MANILA)
    shift_service.ensure_current_shift()

    assert [item.shift_date for item in history_service.list_summaries()] == [
        date(2026, 8, 1)
    ]
    assert [
        item.shift_date for item in history_service.list_summaries(include_open=True)
    ] == [date(2026, 8, 2), date(2026, 8, 1)]


def test_history_reports_missing_shift(tmp_path: Path) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    history_service = HistoryService(storage)

    with pytest.raises(HistoryNotFoundError, match="not found"):
        history_service.get_shift_detail(date(2026, 8, 1))


def test_rollover_marks_every_incomplete_task_missed(tmp_path: Path) -> None:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    storage.save_tasks(
        TaskDocument(
            tasks=[
                make_task("Untimed"),
                make_task("Timed", scheduled_time=time(4)),
                make_task(
                    "One time",
                    recurrence=Recurrence.ONE_TIME,
                    target_shift_date=date(2026, 8, 1),
                ),
            ]
        )
    )
    clock = MutableClock(START)
    shift_service = ShiftService(storage, clock=clock)
    shift_service.ensure_current_shift()

    clock.current = datetime(2026, 8, 2, 12, tzinfo=MANILA)
    shift_service.ensure_current_shift()
    old = next(
        record
        for record in storage.load_daily_records().records
        if record.shift_date == date(2026, 8, 1)
    )

    assert all(item.status is TaskStatus.MISSED for item in old.occurrences)
