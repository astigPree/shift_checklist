"""Validated settings/category changes and shift-boundary reconciliation."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from constants import TaskStatus
from models import AppSettings, SettingsDocument
from models.validation import require_clock_time, require_string
from services.shift_service import ShiftService, ShiftStateError, active_shift_date
from services.storage_service import StorageService


class ResetTimeConfirmationRequired(RuntimeError):
    """Raised when a reset edit would close the active shift immediately."""


class UnsafeResetTimeChange(RuntimeError):
    """Raised when a reset edit would move backward into an already used shift."""


class CategoryInUseError(RuntimeError):
    """Raised when deleting a category without replacing task references."""


SettingsChangedCallback = Callable[[], None]


class SettingsService:
    """Persist settings and keep task/shift state consistent."""

    def __init__(self, storage: StorageService, shift_service: ShiftService) -> None:
        self.storage = storage
        self.shift_service = shift_service
        self._callbacks: list[SettingsChangedCallback] = []

    def get(self) -> AppSettings:
        return AppSettings.from_dict(self.storage.load_settings().settings.to_dict())

    def subscribe(self, callback: SettingsChangedCallback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: SettingsChangedCallback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def update(self, *, confirm_reset_change: bool = False, **changes: Any) -> AppSettings:
        """Validate and save settings, reconciling an immediate boundary change."""

        document = self.storage.load_settings()
        current_settings = document.settings
        reset_value = changes.get("reset_time", current_settings.reset_time)
        new_reset = require_clock_time(reset_value, "settings.reset_time")
        changes["reset_time"] = new_reset
        updated = replace(current_settings, **changes)

        if new_reset != current_settings.reset_time:
            self._apply_reset_change(
                document,
                updated,
                confirm_reset_change=confirm_reset_change,
            )
        else:
            document.settings = updated
            self.storage.save_settings(document)

        self._notify_changed()
        return AppSettings.from_dict(updated.to_dict())

    def add_category(self, name: str) -> AppSettings:
        normalized = require_string(name, "category")
        settings = self.get()
        if normalized.casefold() in {item.casefold() for item in settings.categories}:
            raise ValueError(f"category already exists: {normalized}")
        return self.update(categories=[*settings.categories, normalized])

    def delete_category(self, name: str, *, replacement: str | None = None) -> AppSettings:
        """Delete an unused category or replace every task reference first."""

        category = require_string(name, "category")
        settings = self.get()
        if category not in settings.categories:
            raise ValueError(f"category is not configured: {category}")
        remaining = [item for item in settings.categories if item != category]
        if not remaining:
            raise ValueError("at least one category must remain")

        task_document = self.storage.load_tasks()
        referenced = [task for task in task_document.tasks if task.category == category]
        if referenced:
            if replacement is None:
                raise CategoryInUseError(
                    f"category is used by {len(referenced)} task(s); choose a replacement"
                )
            replacement_name = require_string(replacement, "replacement")
            if replacement_name == category or replacement_name not in remaining:
                raise ValueError("replacement must be another configured category")
            changed_at = self.shift_service.now()
            task_document.tasks = [
                replace(task, category=replacement_name, updated_at=changed_at)
                if task.category == category
                else task
                for task in task_document.tasks
            ]
            self.storage.save_tasks(task_document)
            self.shift_service.synchronize_current_shift(at=changed_at)

        return self.update(categories=remaining)

    def open_data_directory(self) -> Path:
        """Open the resolved storage directory in Windows Explorer."""

        self.storage.data_directory.mkdir(parents=True, exist_ok=True)
        os.startfile(self.storage.data_directory)  # type: ignore[attr-defined]
        return self.storage.data_directory

    def _apply_reset_change(
        self,
        document: SettingsDocument,
        updated: AppSettings,
        *,
        confirm_reset_change: bool,
    ) -> None:
        current = self.shift_service.now()
        old_date = active_shift_date(current, document.settings.reset_time)
        new_date = active_shift_date(current, updated.reset_time)
        if old_date != new_date and not confirm_reset_change:
            raise ResetTimeConfirmationRequired(
                f"Changing reset time closes shift {old_date} and opens shift {new_date}"
            )
        if new_date < old_date:
            raise UnsafeResetTimeChange(
                "This reset time would move into an earlier shift date. Apply it after "
                "the new reset boundary instead."
            )

        if old_date != new_date:
            records = self.storage.load_daily_records()
            existing_target = next(
                (record for record in records.records if record.shift_date == new_date),
                None,
            )
            if existing_target is not None and existing_target.is_closed:
                raise ShiftStateError(
                    f"Cannot open shift {new_date}; its historical record is already closed"
                )
            open_record = next(
                (record for record in records.records if not record.is_closed), None
            )
            if open_record is not None:
                for occurrence in open_record.occurrences:
                    if occurrence.status is TaskStatus.PENDING:
                        occurrence.status = TaskStatus.MISSED
                open_record.closed_at = current
                self.storage.save_daily_records(records)

        document.settings = updated
        self.storage.save_settings(document)
        if old_date != new_date:
            self.shift_service.ensure_current_shift(at=current)

    def _notify_changed(self) -> None:
        for callback in tuple(self._callbacks):
            callback()
