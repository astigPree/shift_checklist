"""Task template CRUD, occurrence completion, filtering, and live state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from constants import LiveTaskState, ShopifyStatus, TaskStatus, TaskType
from models import (
    DailyRecord,
    DailyRecordsDocument,
    ShopifyDetails,
    TaskDocument,
    TaskOccurrence,
    TaskTemplate,
)
from models.validation import require_aware_datetime, require_enum, require_uuid
from services.shift_service import ShiftService
from services.storage_service import StorageService

DUE_DISPLAY_WINDOW = timedelta(minutes=1)


class TaskNotFoundError(LookupError):
    """Raised when a requested task template or occurrence does not exist."""


class ConfirmationRequiredError(RuntimeError):
    """Raised when deletion is attempted without explicit confirmation."""


class CategoryNotFoundError(ValueError):
    """Raised when a task references a category absent from settings."""


@dataclass(frozen=True, slots=True)
class OccurrenceView:
    """Read-only occurrence snapshot plus its derived display state and due time."""

    occurrence: TaskOccurrence
    state: LiveTaskState
    due_at: datetime | None


class TaskService:
    """Coordinate task mutations across templates and the active shift."""

    def __init__(self, storage: StorageService, shift_service: ShiftService) -> None:
        self.storage = storage
        self.shift_service = shift_service

    def list_templates(self, *, include_disabled: bool = True) -> list[TaskTemplate]:
        templates = self.storage.load_tasks().tasks
        if not include_disabled:
            templates = [template for template in templates if template.enabled]
        return [
            TaskTemplate.from_dict(template.to_dict())
            for template in sorted(
                templates, key=lambda item: (item.sort_order, item.title, item.id)
            )
        ]

    def add_task(self, template: TaskTemplate) -> TaskTemplate:
        """Persist a new template and materialize it when applicable now."""

        document = self.storage.load_tasks()
        candidate = TaskTemplate.from_dict(template.to_dict())
        if any(existing.id == candidate.id for existing in document.tasks):
            raise ValueError(f"task ID already exists: {candidate.id}")
        self._validate_category(candidate.category)
        candidate.sort_order = (
            max((existing.sort_order for existing in document.tasks), default=-1) + 1
        )
        document.tasks.append(candidate)
        self.storage.save_tasks(document)
        self.shift_service.synchronize_current_shift()
        return TaskTemplate.from_dict(candidate.to_dict())

    def update_task(self, task_id: str, **changes: Any) -> TaskTemplate:
        """Apply validated fields while preserving identity and creation time."""

        identifier = require_uuid(task_id, "task_id")
        forbidden = {"id", "created_at"}.intersection(changes)
        if forbidden:
            raise ValueError(f"cannot update protected task fields: {', '.join(sorted(forbidden))}")
        document = self.storage.load_tasks()
        index, existing = self._find_template(document, identifier)
        updated = replace(existing, **changes, updated_at=self.shift_service.now())
        self._validate_category(updated.category)
        document.tasks[index] = updated
        self.storage.save_tasks(document)
        self.shift_service.synchronize_current_shift()
        return TaskTemplate.from_dict(updated.to_dict())

    def set_enabled(self, task_id: str, enabled: bool) -> TaskTemplate:
        return self.update_task(task_id, enabled=enabled)

    def delete_task(self, task_id: str, *, confirmed: bool = False) -> None:
        """Delete a template only after confirmation; closed history is untouched."""

        if not confirmed:
            raise ConfirmationRequiredError("task deletion requires confirmation")
        identifier = require_uuid(task_id, "task_id")
        document = self.storage.load_tasks()
        index, _existing = self._find_template(document, identifier)
        del document.tasks[index]
        self.storage.save_tasks(document)
        self.shift_service.synchronize_current_shift()

    def reorder_tasks(self, ordered_task_ids: Iterable[str]) -> list[TaskTemplate]:
        """Assign stable contiguous sort values using every current template ID."""

        identifiers = [require_uuid(value, "ordered_task_ids") for value in ordered_task_ids]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("ordered_task_ids cannot contain duplicates")
        document = self.storage.load_tasks()
        current_ids = {template.id for template in document.tasks}
        if set(identifiers) != current_ids:
            raise ValueError("ordered_task_ids must contain every current task exactly once")
        by_id = {template.id: template for template in document.tasks}
        changed_at = self.shift_service.now()
        document.tasks = [
            replace(by_id[identifier], sort_order=index, updated_at=changed_at)
            for index, identifier in enumerate(identifiers)
        ]
        self.storage.save_tasks(document)
        self.shift_service.synchronize_current_shift()
        return self.list_templates()

    def complete_occurrence(
        self, occurrence_id: str, *, completed_at: datetime | None = None
    ) -> TaskOccurrence:
        """Complete one active occurrence and save its timestamp immediately."""

        timestamp = require_aware_datetime(
            completed_at or self.shift_service.now(), "completed_at"
        )
        document, record, index, occurrence = self._active_occurrence(occurrence_id)
        if occurrence.status is TaskStatus.COMPLETED:
            return TaskOccurrence.from_dict(occurrence.to_dict())
        if occurrence.task_type is TaskType.SHOPIFY:
            details = self._shopify_details(occurrence)
            occurrence.shopify_details = replace(
                details,
                status=ShopifyStatus.COMPLETED,
                completed_at=timestamp,
            )
            self._update_shopify_template(
                occurrence.template_id,
                status=ShopifyStatus.COMPLETED,
                completed_at=timestamp,
            )
        occurrence.status = TaskStatus.COMPLETED
        occurrence.completed_at = timestamp
        record.occurrences[index] = occurrence
        self.storage.save_daily_records(document)
        return TaskOccurrence.from_dict(occurrence.to_dict())

    def reopen_occurrence(self, occurrence_id: str) -> TaskOccurrence:
        """Return a completed active occurrence to pending and clear its timestamp."""

        document, record, index, occurrence = self._active_occurrence(occurrence_id)
        if occurrence.status is TaskStatus.PENDING:
            return TaskOccurrence.from_dict(occurrence.to_dict())
        occurrence.status = TaskStatus.PENDING
        occurrence.completed_at = None
        if occurrence.task_type is TaskType.SHOPIFY:
            details = self._shopify_details(occurrence)
            occurrence.shopify_details = replace(
                details,
                status=ShopifyStatus.PENDING,
                completed_at=None,
            )
            self._update_shopify_template(
                occurrence.template_id,
                status=ShopifyStatus.PENDING,
                completed_at=None,
            )
        record.occurrences[index] = occurrence
        self.storage.save_daily_records(document)
        return TaskOccurrence.from_dict(occurrence.to_dict())

    def set_shopify_status(
        self,
        occurrence_id: str,
        status: ShopifyStatus | str,
        *,
        changed_at: datetime | None = None,
    ) -> TaskOccurrence:
        """Transition Shopify workflow status and synchronize completion state."""

        target_status = require_enum(status, ShopifyStatus, "shopify_status")
        timestamp = require_aware_datetime(
            changed_at or self.shift_service.now(), "changed_at"
        )
        document, record, index, occurrence = self._active_occurrence(occurrence_id)
        details = self._shopify_details(occurrence)
        if details.status is target_status:
            return TaskOccurrence.from_dict(occurrence.to_dict())
        completed_at = timestamp if target_status is ShopifyStatus.COMPLETED else None
        occurrence.shopify_details = replace(
            details,
            status=target_status,
            completed_at=completed_at,
        )
        occurrence.status = (
            TaskStatus.COMPLETED
            if target_status is ShopifyStatus.COMPLETED
            else TaskStatus.PENDING
        )
        occurrence.completed_at = completed_at
        record.occurrences[index] = occurrence
        self._update_shopify_template(
            occurrence.template_id,
            status=target_status,
            completed_at=completed_at,
        )
        self.storage.save_daily_records(document)
        return TaskOccurrence.from_dict(occurrence.to_dict())

    def live_state(
        self, occurrence: TaskOccurrence, *, at: datetime | None = None
    ) -> LiveTaskState:
        """Calculate a display state without changing persisted status."""

        if occurrence.status is TaskStatus.COMPLETED:
            return LiveTaskState.COMPLETED
        if occurrence.status is TaskStatus.MISSED:
            return LiveTaskState.MISSED
        if occurrence.scheduled_time is None:
            return LiveTaskState.PENDING
        current = require_aware_datetime(at or self.shift_service.now(), "at")
        due_at = self.shift_service.due_at(occurrence, at=current)
        if due_at is None:
            return LiveTaskState.PENDING
        if current < due_at:
            return LiveTaskState.UPCOMING
        if current < due_at + DUE_DISPLAY_WINDOW:
            return LiveTaskState.DUE
        return LiveTaskState.OVERDUE

    def list_occurrences(
        self,
        *,
        category: str | None = None,
        states: set[LiveTaskState] | None = None,
        at: datetime | None = None,
    ) -> list[OccurrenceView]:
        """Return filtered, ordered snapshots for the active shift UI."""

        current = require_aware_datetime(at or self.shift_service.now(), "at")
        record = self.shift_service.ensure_current_shift(at=current)
        views: list[OccurrenceView] = []
        for occurrence in record.occurrences:
            if category is not None and occurrence.category != category:
                continue
            state = self.live_state(occurrence, at=current)
            if states is not None and state not in states:
                continue
            views.append(
                OccurrenceView(
                    TaskOccurrence.from_dict(occurrence.to_dict()),
                    state,
                    self.shift_service.due_at(occurrence, at=current),
                )
            )
        return sorted(
            views,
            key=lambda view: (
                view.occurrence.sort_order,
                view.occurrence.title,
                view.occurrence.id,
            ),
        )

    def _validate_category(self, category: str) -> None:
        categories = self.storage.load_settings().settings.categories
        if category not in categories:
            raise CategoryNotFoundError(f"category is not configured: {category}")

    @staticmethod
    def _find_template(
        document: TaskDocument, task_id: str
    ) -> tuple[int, TaskTemplate]:
        for index, template in enumerate(document.tasks):
            if template.id == task_id:
                return index, template
        raise TaskNotFoundError(f"task template not found: {task_id}")

    def _active_occurrence(
        self, occurrence_id: str
    ) -> tuple[DailyRecordsDocument, DailyRecord, int, TaskOccurrence]:
        identifier = require_uuid(occurrence_id, "occurrence_id")
        current = self.shift_service.now()
        current_date = self.shift_service.ensure_current_shift(at=current).shift_date
        document = self.storage.load_daily_records()
        record = next(
            (
                item
                for item in document.records
                if item.shift_date == current_date and not item.is_closed
            ),
            None,
        )
        if record is None:
            raise TaskNotFoundError("active shift record not found")
        for index, occurrence in enumerate(record.occurrences):
            if occurrence.id == identifier:
                return document, record, index, occurrence
        raise TaskNotFoundError(f"task occurrence not found in active shift: {identifier}")

    @staticmethod
    def _shopify_details(occurrence: TaskOccurrence) -> ShopifyDetails:
        if occurrence.task_type is not TaskType.SHOPIFY or occurrence.shopify_details is None:
            raise ValueError("occurrence is not a Shopify task")
        return occurrence.shopify_details

    def _update_shopify_template(
        self,
        template_id: str,
        *,
        status: ShopifyStatus,
        completed_at: datetime | None,
    ) -> None:
        document = self.storage.load_tasks()
        index, template = self._find_template(document, template_id)
        if template.task_type is not TaskType.SHOPIFY or template.shopify_details is None:
            raise ValueError("Shopify occurrence template is invalid")
        document.tasks[index] = replace(
            template,
            shopify_details=replace(
                template.shopify_details,
                status=status,
                completed_at=completed_at,
            ),
            updated_at=self.shift_service.now(),
        )
        self.storage.save_tasks(document)
