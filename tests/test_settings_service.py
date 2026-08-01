"""Tests for settings updates, reset transitions, and category management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from constants import TaskStatus
from models import TaskDocument, TaskTemplate
from services import (
    CategoryInUseError,
    ResetTimeConfirmationRequired,
    SettingsService,
    ShiftService,
    StorageService,
    UnsafeResetTimeChange,
)

MANILA = timezone(timedelta(hours=8))


@dataclass
class MutableClock:
    current: datetime

    def __call__(self) -> datetime:
        return self.current


def make_services(
    tmp_path: Path,
    *,
    current: datetime,
    task: TaskTemplate | None = None,
) -> tuple[StorageService, ShiftService, SettingsService]:
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    if task is not None:
        storage.save_tasks(TaskDocument(tasks=[task]))
    shift_service = ShiftService(storage, clock=MutableClock(current))
    shift_service.ensure_current_shift()
    return storage, shift_service, SettingsService(storage, shift_service)


def test_regular_settings_update_saves_and_notifies(tmp_path: Path) -> None:
    storage, _shift, settings_service = make_services(
        tmp_path, current=datetime(2026, 8, 1, 20, tzinfo=MANILA)
    )
    callbacks: list[str] = []
    settings_service.subscribe(lambda: callbacks.append("changed"))

    updated = settings_service.update(
        notifications_enabled=False,
        client_check_interval_minutes=45,
    )

    assert updated.notifications_enabled is False
    assert storage.load_settings().settings.client_check_interval_minutes == 45
    assert callbacks == ["changed"]


def test_reset_change_that_advances_shift_requires_confirmation(tmp_path: Path) -> None:
    storage, shift, settings_service = make_services(
        tmp_path, current=datetime(2026, 8, 2, 10, tzinfo=MANILA)
    )

    with pytest.raises(ResetTimeConfirmationRequired):
        settings_service.update(reset_time=time(8))

    assert storage.load_settings().settings.reset_time == time(12)
    updated = settings_service.update(reset_time=time(8), confirm_reset_change=True)
    records = storage.load_daily_records().records
    old = next(record for record in records if record.shift_date == date(2026, 8, 1))

    assert updated.reset_time == time(8)
    assert old.closed_at == datetime(2026, 8, 2, 10, tzinfo=MANILA)
    assert shift.ensure_current_shift().shift_date == date(2026, 8, 2)


def test_reset_change_marks_pending_occurrences_missed(tmp_path: Path) -> None:
    created = datetime(2026, 8, 1, 20, tzinfo=MANILA)
    task = TaskTemplate(
        title="Pending",
        category="General",
        created_at=created,
        updated_at=created,
    )
    storage, _shift, settings_service = make_services(
        tmp_path,
        current=datetime(2026, 8, 2, 10, tzinfo=MANILA),
        task=task,
    )

    settings_service.update(reset_time=time(8), confirm_reset_change=True)

    old = next(
        record
        for record in storage.load_daily_records().records
        if record.shift_date == date(2026, 8, 1)
    )
    assert old.occurrences[0].status is TaskStatus.MISSED


def test_reset_change_that_moves_backward_is_refused(tmp_path: Path) -> None:
    storage, _shift, settings_service = make_services(
        tmp_path, current=datetime(2026, 8, 2, 10, tzinfo=MANILA)
    )
    document = storage.load_settings()
    document.settings.reset_time = time(8)
    storage.save_settings(document)

    with pytest.raises(UnsafeResetTimeChange):
        settings_service.update(reset_time=time(12), confirm_reset_change=True)


def test_category_add_and_duplicate_validation(tmp_path: Path) -> None:
    _storage, _shift, settings_service = make_services(
        tmp_path, current=datetime(2026, 8, 1, 20, tzinfo=MANILA)
    )

    updated = settings_service.add_category("Custom")
    assert "Custom" in updated.categories

    with pytest.raises(ValueError, match="already exists"):
        settings_service.add_category(" custom ")


def test_category_in_use_requires_and_applies_replacement(tmp_path: Path) -> None:
    created = datetime(2026, 8, 1, 20, tzinfo=MANILA)
    task = TaskTemplate(
        title="Attendance",
        category="FastDTR",
        created_at=created,
        updated_at=created,
    )
    storage, shift, settings_service = make_services(
        tmp_path,
        current=created,
        task=task,
    )

    with pytest.raises(CategoryInUseError, match="replacement"):
        settings_service.delete_category("FastDTR")

    updated = settings_service.delete_category("FastDTR", replacement="General")

    assert "FastDTR" not in updated.categories
    assert storage.load_tasks().tasks[0].category == "General"
    assert shift.ensure_current_shift().occurrences[0].category == "General"


def test_unused_category_can_be_deleted_without_replacement(tmp_path: Path) -> None:
    _storage, _shift, settings_service = make_services(
        tmp_path, current=datetime(2026, 8, 1, 20, tzinfo=MANILA)
    )

    updated = settings_service.delete_category("Shopify")

    assert "Shopify" not in updated.categories
