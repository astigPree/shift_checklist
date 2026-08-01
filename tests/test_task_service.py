"""Tests for task CRUD, active occurrences, live states, and Shopify workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from constants import LiveTaskState, Recurrence, ShopifyStatus, TaskStatus, TaskType
from models import ShopifyDetails, TaskTemplate
from services import (
    CategoryNotFoundError,
    ConfirmationRequiredError,
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


@pytest.fixture
def task_context(tmp_path: Path) -> tuple[StorageService, MutableClock, ShiftService, TaskService]:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    clock = MutableClock(datetime(2026, 8, 1, 20, tzinfo=MANILA))
    shift_service = ShiftService(storage, clock=clock)
    task_service = TaskService(storage, shift_service)
    shift_service.ensure_current_shift()
    return storage, clock, shift_service, task_service


def make_task(title: str, **changes: object) -> TaskTemplate:
    values: dict[str, object] = {
        "title": title,
        "category": "General",
        "created_at": datetime(2026, 8, 1, 20, tzinfo=MANILA),
        "updated_at": datetime(2026, 8, 1, 20, tzinfo=MANILA),
    }
    values.update(changes)
    return TaskTemplate(**values)  # type: ignore[arg-type]


def test_add_and_edit_task_updates_active_occurrence(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context

    created = task_service.add_task(make_task("Original"))
    updated = task_service.update_task(created.id, title="Edited", notes="Updated note")
    record = shift_service.ensure_current_shift()

    assert updated.title == "Edited"
    assert len(record.occurrences) == 1
    assert record.occurrences[0].title == "Edited"
    assert record.occurrences[0].notes == "Updated note"


def test_add_task_requires_configured_category(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, _shift_service, task_service = task_context

    with pytest.raises(CategoryNotFoundError, match="not configured"):
        task_service.add_task(make_task("Unknown", category="Not configured"))


def test_update_rejects_protected_identity_fields(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, _shift_service, task_service = task_context
    created = task_service.add_task(make_task("Protected"))

    with pytest.raises(ValueError, match="protected"):
        task_service.update_task(created.id, id=created.id)


def test_delete_requires_confirmation_and_removes_pending_occurrence(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    storage, _clock, shift_service, task_service = task_context
    created = task_service.add_task(make_task("Delete me"))

    with pytest.raises(ConfirmationRequiredError):
        task_service.delete_task(created.id)

    task_service.delete_task(created.id, confirmed=True)

    assert storage.load_tasks().tasks == []
    assert shift_service.ensure_current_shift().occurrences == []


def test_deleting_template_keeps_completed_open_occurrence(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context
    created = task_service.add_task(make_task("Keep completion"))
    occurrence = shift_service.ensure_current_shift().occurrences[0]
    task_service.complete_occurrence(occurrence.id)

    task_service.delete_task(created.id, confirmed=True)

    retained = shift_service.ensure_current_shift().occurrences
    assert len(retained) == 1
    assert retained[0].status is TaskStatus.COMPLETED


def test_disable_and_reenable_controls_current_occurrence(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context
    created = task_service.add_task(make_task("Toggle me"))
    original_id = shift_service.ensure_current_shift().occurrences[0].id

    task_service.set_enabled(created.id, False)
    assert shift_service.ensure_current_shift().occurrences == []

    task_service.set_enabled(created.id, True)
    enabled = shift_service.ensure_current_shift().occurrences
    assert len(enabled) == 1
    assert enabled[0].id != original_id


def test_reorder_updates_templates_and_occurrences(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context
    first = task_service.add_task(make_task("First"))
    second = task_service.add_task(make_task("Second"))
    third = task_service.add_task(make_task("Third"))

    reordered = task_service.reorder_tasks([third.id, first.id, second.id])

    assert [item.title for item in reordered] == ["Third", "First", "Second"]
    assert [item.title for item in shift_service.ensure_current_shift().occurrences] == [
        "Third",
        "First",
        "Second",
    ]


def test_reorder_rejects_incomplete_or_duplicate_id_lists(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, _shift_service, task_service = task_context
    first = task_service.add_task(make_task("First"))
    second = task_service.add_task(make_task("Second"))

    with pytest.raises(ValueError, match="every current task"):
        task_service.reorder_tasks([first.id])
    with pytest.raises(ValueError, match="duplicates"):
        task_service.reorder_tasks([first.id, first.id, second.id])


def test_complete_is_idempotent_and_reopen_clears_timestamp(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context
    task_service.add_task(make_task("Complete me"))
    occurrence = shift_service.ensure_current_shift().occurrences[0]
    completed_at = datetime(2026, 8, 1, 21, tzinfo=MANILA)

    first = task_service.complete_occurrence(occurrence.id, completed_at=completed_at)
    second = task_service.complete_occurrence(
        occurrence.id,
        completed_at=completed_at + timedelta(hours=1),
    )
    reopened = task_service.reopen_occurrence(occurrence.id)

    assert first.completed_at == completed_at
    assert second.completed_at == completed_at
    assert reopened.status is TaskStatus.PENDING
    assert reopened.completed_at is None


def test_closed_history_snapshot_does_not_change_after_template_edit(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    storage, clock, shift_service, task_service = task_context
    template = task_service.add_task(make_task("Historical title"))
    shift_service.ensure_current_shift()

    clock.current = datetime(2026, 8, 2, 12, tzinfo=MANILA)
    shift_service.ensure_current_shift()
    task_service.update_task(template.id, title="Current title")

    old_record = next(
        record
        for record in storage.load_daily_records().records
        if record.shift_date == date(2026, 8, 1)
    )
    assert old_record.occurrences[0].title == "Historical title"


def test_live_state_boundaries_and_filtering(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, clock, _shift_service, task_service = task_context
    task_service.add_task(make_task("Untimed"))
    task_service.add_task(make_task("Four AM", scheduled_time=time(4)))
    occurrences = {view.occurrence.title: view.occurrence for view in task_service.list_occurrences()}
    timed = occurrences["Four AM"]
    untimed = occurrences["Untimed"]

    assert task_service.live_state(untimed) is LiveTaskState.PENDING
    clock.current = datetime(2026, 8, 2, 3, 59, tzinfo=MANILA)
    assert task_service.live_state(timed) is LiveTaskState.UPCOMING
    clock.current = datetime(2026, 8, 2, 4, 0, 30, tzinfo=MANILA)
    assert task_service.live_state(timed) is LiveTaskState.DUE
    clock.current = datetime(2026, 8, 2, 4, 1, tzinfo=MANILA)
    assert task_service.live_state(timed) is LiveTaskState.OVERDUE

    overdue = task_service.list_occurrences(states={LiveTaskState.OVERDUE})
    assert [view.occurrence.title for view in overdue] == ["Four AM"]


def test_one_time_task_materializes_only_for_target_shift(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, shift_service, task_service = task_context
    task_service.add_task(
        make_task(
            "Today only",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 1),
        )
    )
    task_service.add_task(
        make_task(
            "Tomorrow only",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 2),
        )
    )

    assert [item.title for item in shift_service.ensure_current_shift().occurrences] == [
        "Today only"
    ]


def test_shopify_status_transitions_synchronize_task_completion(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    storage, _clock, shift_service, task_service = task_context
    details = ShopifyDetails(
        store_name="Example Store",
        description="Update banner",
        requested_at=datetime(2026, 8, 1, 20, tzinfo=MANILA),
    )
    template = task_service.add_task(
        make_task(
            "Update banner",
            category="Shopify",
            recurrence=Recurrence.ONE_TIME,
            target_shift_date=date(2026, 8, 1),
            task_type=TaskType.SHOPIFY,
            shopify_details=details,
        )
    )
    occurrence = shift_service.ensure_current_shift().occurrences[0]

    in_progress = task_service.set_shopify_status(
        occurrence.id, ShopifyStatus.IN_PROGRESS
    )
    completed_at = datetime(2026, 8, 1, 22, tzinfo=MANILA)
    completed = task_service.set_shopify_status(
        occurrence.id,
        ShopifyStatus.COMPLETED,
        changed_at=completed_at,
    )
    reopened = task_service.set_shopify_status(
        occurrence.id, ShopifyStatus.READY_FOR_REVIEW
    )
    persisted_template = next(
        item for item in storage.load_tasks().tasks if item.id == template.id
    )

    assert in_progress.status is TaskStatus.PENDING
    assert in_progress.shopify_details.status is ShopifyStatus.IN_PROGRESS  # type: ignore[union-attr]
    assert completed.status is TaskStatus.COMPLETED
    assert completed.completed_at == completed_at
    assert reopened.status is TaskStatus.PENDING
    assert reopened.completed_at is None
    assert persisted_template.shopify_details is not None
    assert persisted_template.shopify_details.status is ShopifyStatus.READY_FOR_REVIEW


def test_category_filter_returns_only_matching_occurrences(
    task_context: tuple[StorageService, MutableClock, ShiftService, TaskService],
) -> None:
    _storage, _clock, _shift_service, task_service = task_context
    task_service.add_task(make_task("General"))
    task_service.add_task(make_task("Attendance", category="FastDTR"))

    filtered = task_service.list_occurrences(category="FastDTR")

    assert [view.occurrence.title for view in filtered] == ["Attendance"]
