"""Task template, occurrence, and Shopify domain models."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from uuid import uuid4

from constants import (
    DEFAULT_REMINDER_LEAD_MINUTES,
    SCHEMA_VERSION,
    Priority,
    Recurrence,
    ShopifyStatus,
    TaskStatus,
    TaskType,
)
from models.validation import (
    ModelValidationError,
    collect_extra,
    merge_extra,
    optional_aware_datetime,
    optional_clock_time,
    optional_date,
    require_aware_datetime,
    require_bool,
    require_date,
    require_enum,
    require_int,
    require_list,
    require_mapping,
    require_string,
    require_uuid,
    serialize_clock_time,
    serialize_date,
    serialize_datetime,
)


def _local_now() -> datetime:
    return datetime.now().astimezone()


@dataclass(slots=True)
class ShopifyDetails:
    """Manual Shopify request details; no remote credentials are stored."""

    store_name: str
    description: str
    requested_at: datetime
    priority: Priority = Priority.NORMAL
    status: ShopifyStatus = ShopifyStatus.PENDING
    completed_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.store_name = require_string(self.store_name, "shopify_details.store_name")
        self.description = require_string(self.description, "shopify_details.description")
        self.requested_at = require_aware_datetime(
            self.requested_at, "shopify_details.requested_at"
        )
        self.priority = require_enum(self.priority, Priority, "shopify_details.priority")
        self.status = require_enum(self.status, ShopifyStatus, "shopify_details.status")
        self.completed_at = optional_aware_datetime(
            self.completed_at, "shopify_details.completed_at"
        )
        if self.status is ShopifyStatus.COMPLETED and self.completed_at is None:
            raise ModelValidationError(
                "shopify_details.completed_at is required when status is Completed"
            )
        if self.status is not ShopifyStatus.COMPLETED and self.completed_at is not None:
            raise ModelValidationError(
                "shopify_details.completed_at must be empty unless status is Completed"
            )

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "store_name": self.store_name,
                "description": self.description,
                "requested_at": serialize_datetime(self.requested_at),
                "priority": self.priority.value,
                "status": self.status.value,
                "completed_at": serialize_datetime(self.completed_at),
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> ShopifyDetails:
        data = require_mapping(value, "shopify_details")
        known = {
            "store_name",
            "description",
            "requested_at",
            "priority",
            "status",
            "completed_at",
        }
        return cls(
            store_name=require_string(data.get("store_name"), "shopify_details.store_name"),
            description=require_string(
                data.get("description"), "shopify_details.description"
            ),
            requested_at=require_aware_datetime(
                data.get("requested_at"), "shopify_details.requested_at"
            ),
            priority=require_enum(
                data.get("priority", Priority.NORMAL.value),
                Priority,
                "shopify_details.priority",
            ),
            status=require_enum(
                data.get("status", ShopifyStatus.PENDING.value),
                ShopifyStatus,
                "shopify_details.status",
            ),
            completed_at=optional_aware_datetime(
                data.get("completed_at"), "shopify_details.completed_at"
            ),
            extra=collect_extra(data, known),
        )


@dataclass(slots=True)
class TaskTemplate:
    """Reusable definition from which shift occurrences are created."""

    title: str
    category: str
    id: str = field(default_factory=lambda: str(uuid4()))
    notes: str = ""
    scheduled_time: time | None = None
    reminder_enabled: bool = False
    reminder_lead_minutes: int = DEFAULT_REMINDER_LEAD_MINUTES
    recurrence: Recurrence = Recurrence.DAILY
    target_shift_date: date | None = None
    enabled: bool = True
    sort_order: int = 0
    task_type: TaskType = TaskType.GENERAL
    shopify_details: ShopifyDetails | None = None
    created_at: datetime = field(default_factory=_local_now)
    updated_at: datetime = field(default_factory=_local_now)
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.id = require_uuid(self.id, "task.id")
        self.title = require_string(self.title, "task.title")
        self.category = require_string(self.category, "task.category")
        self.notes = require_string(self.notes, "task.notes", allow_blank=True)
        self.scheduled_time = optional_clock_time(self.scheduled_time, "task.scheduled_time")
        self.reminder_enabled = require_bool(self.reminder_enabled, "task.reminder_enabled")
        self.reminder_lead_minutes = require_int(
            self.reminder_lead_minutes, "task.reminder_lead_minutes", minimum=0
        )
        self.recurrence = require_enum(self.recurrence, Recurrence, "task.recurrence")
        self.target_shift_date = optional_date(
            self.target_shift_date, "task.target_shift_date"
        )
        self.enabled = require_bool(self.enabled, "task.enabled")
        self.sort_order = require_int(self.sort_order, "task.sort_order", minimum=0)
        self.task_type = require_enum(self.task_type, TaskType, "task.task_type")
        self.created_at = require_aware_datetime(self.created_at, "task.created_at")
        self.updated_at = require_aware_datetime(self.updated_at, "task.updated_at")

        if self.updated_at < self.created_at:
            raise ModelValidationError("task.updated_at cannot be before task.created_at")
        if self.recurrence is Recurrence.ONE_TIME and self.target_shift_date is None:
            raise ModelValidationError("one-time tasks require task.target_shift_date")
        if self.recurrence is Recurrence.DAILY and self.target_shift_date is not None:
            raise ModelValidationError("daily tasks cannot have task.target_shift_date")
        if self.reminder_enabled and self.scheduled_time is None:
            raise ModelValidationError("task reminders require task.scheduled_time")
        if self.task_type is TaskType.SHOPIFY:
            if self.shopify_details is None:
                raise ModelValidationError("Shopify tasks require task.shopify_details")
            if self.recurrence is not Recurrence.ONE_TIME:
                raise ModelValidationError("Shopify tasks must be one-time tasks")
        elif self.shopify_details is not None:
            raise ModelValidationError("general tasks cannot contain task.shopify_details")

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "id": self.id,
                "title": self.title,
                "category": self.category,
                "notes": self.notes,
                "scheduled_time": serialize_clock_time(self.scheduled_time),
                "reminder_enabled": self.reminder_enabled,
                "reminder_lead_minutes": self.reminder_lead_minutes,
                "recurrence": self.recurrence.value,
                "target_shift_date": serialize_date(self.target_shift_date),
                "enabled": self.enabled,
                "sort_order": self.sort_order,
                "task_type": self.task_type.value,
                "shopify_details": (
                    self.shopify_details.to_dict() if self.shopify_details else None
                ),
                "created_at": serialize_datetime(self.created_at),
                "updated_at": serialize_datetime(self.updated_at),
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> TaskTemplate:
        data = require_mapping(value, "task")
        known = {
            "id",
            "title",
            "category",
            "notes",
            "scheduled_time",
            "reminder_enabled",
            "reminder_lead_minutes",
            "recurrence",
            "target_shift_date",
            "enabled",
            "sort_order",
            "task_type",
            "shopify_details",
            "created_at",
            "updated_at",
        }
        shopify_value = data.get("shopify_details")
        return cls(
            id=require_uuid(data.get("id"), "task.id"),
            title=require_string(data.get("title"), "task.title"),
            category=require_string(data.get("category"), "task.category"),
            notes=require_string(data.get("notes", ""), "task.notes", allow_blank=True),
            scheduled_time=optional_clock_time(
                data.get("scheduled_time"), "task.scheduled_time"
            ),
            reminder_enabled=require_bool(
                data.get("reminder_enabled", False), "task.reminder_enabled"
            ),
            reminder_lead_minutes=require_int(
                data.get("reminder_lead_minutes", DEFAULT_REMINDER_LEAD_MINUTES),
                "task.reminder_lead_minutes",
                minimum=0,
            ),
            recurrence=require_enum(
                data.get("recurrence", Recurrence.DAILY.value), Recurrence, "task.recurrence"
            ),
            target_shift_date=optional_date(
                data.get("target_shift_date"), "task.target_shift_date"
            ),
            enabled=require_bool(data.get("enabled", True), "task.enabled"),
            sort_order=require_int(data.get("sort_order", 0), "task.sort_order", minimum=0),
            task_type=require_enum(
                data.get("task_type", TaskType.GENERAL.value), TaskType, "task.task_type"
            ),
            shopify_details=(
                ShopifyDetails.from_dict(shopify_value) if shopify_value is not None else None
            ),
            created_at=require_aware_datetime(data.get("created_at"), "task.created_at"),
            updated_at=require_aware_datetime(data.get("updated_at"), "task.updated_at"),
            extra=collect_extra(data, known),
        )


@dataclass(slots=True)
class TaskOccurrence:
    """Per-shift snapshot of a task template and its completion state."""

    template_id: str
    shift_date: date
    title: str
    category: str
    id: str = field(default_factory=lambda: str(uuid4()))
    notes: str = ""
    scheduled_time: time | None = None
    reminder_enabled: bool = False
    reminder_lead_minutes: int = DEFAULT_REMINDER_LEAD_MINUTES
    sort_order: int = 0
    task_type: TaskType = TaskType.GENERAL
    shopify_details: ShopifyDetails | None = None
    status: TaskStatus = TaskStatus.PENDING
    completed_at: datetime | None = None
    pre_due_reminder_fired: bool = False
    due_reminder_fired: bool = False
    created_at: datetime = field(default_factory=_local_now)
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.id = require_uuid(self.id, "occurrence.id")
        self.template_id = require_uuid(self.template_id, "occurrence.template_id")
        self.shift_date = require_date(self.shift_date, "occurrence.shift_date")
        self.title = require_string(self.title, "occurrence.title")
        self.category = require_string(self.category, "occurrence.category")
        self.notes = require_string(self.notes, "occurrence.notes", allow_blank=True)
        self.scheduled_time = optional_clock_time(
            self.scheduled_time, "occurrence.scheduled_time"
        )
        self.reminder_enabled = require_bool(
            self.reminder_enabled, "occurrence.reminder_enabled"
        )
        self.reminder_lead_minutes = require_int(
            self.reminder_lead_minutes,
            "occurrence.reminder_lead_minutes",
            minimum=0,
        )
        self.sort_order = require_int(self.sort_order, "occurrence.sort_order", minimum=0)
        self.task_type = require_enum(self.task_type, TaskType, "occurrence.task_type")
        self.status = require_enum(self.status, TaskStatus, "occurrence.status")
        self.completed_at = optional_aware_datetime(
            self.completed_at, "occurrence.completed_at"
        )
        self.pre_due_reminder_fired = require_bool(
            self.pre_due_reminder_fired, "occurrence.pre_due_reminder_fired"
        )
        self.due_reminder_fired = require_bool(
            self.due_reminder_fired, "occurrence.due_reminder_fired"
        )
        self.created_at = require_aware_datetime(self.created_at, "occurrence.created_at")

        if self.reminder_enabled and self.scheduled_time is None:
            raise ModelValidationError("occurrence reminders require a scheduled time")
        if self.status is TaskStatus.COMPLETED and self.completed_at is None:
            raise ModelValidationError("completed occurrences require occurrence.completed_at")
        if self.status is not TaskStatus.COMPLETED and self.completed_at is not None:
            raise ModelValidationError(
                "occurrence.completed_at must be empty unless status is completed"
            )
        if self.task_type is TaskType.SHOPIFY and self.shopify_details is None:
            raise ModelValidationError("Shopify occurrences require shopify_details")
        if self.task_type is TaskType.GENERAL and self.shopify_details is not None:
            raise ModelValidationError("general occurrences cannot contain shopify_details")

    @classmethod
    def from_template(cls, template: TaskTemplate, shift_date: date) -> TaskOccurrence:
        """Create an independent occurrence snapshot from a template."""

        shopify_copy = (
            ShopifyDetails.from_dict(deepcopy(template.shopify_details.to_dict()))
            if template.shopify_details
            else None
        )
        return cls(
            template_id=template.id,
            shift_date=shift_date,
            title=template.title,
            category=template.category,
            notes=template.notes,
            scheduled_time=template.scheduled_time,
            reminder_enabled=template.reminder_enabled,
            reminder_lead_minutes=template.reminder_lead_minutes,
            sort_order=template.sort_order,
            task_type=template.task_type,
            shopify_details=shopify_copy,
        )

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "id": self.id,
                "template_id": self.template_id,
                "shift_date": serialize_date(self.shift_date),
                "title": self.title,
                "category": self.category,
                "notes": self.notes,
                "scheduled_time": serialize_clock_time(self.scheduled_time),
                "reminder_enabled": self.reminder_enabled,
                "reminder_lead_minutes": self.reminder_lead_minutes,
                "sort_order": self.sort_order,
                "task_type": self.task_type.value,
                "shopify_details": (
                    self.shopify_details.to_dict() if self.shopify_details else None
                ),
                "status": self.status.value,
                "completed_at": serialize_datetime(self.completed_at),
                "pre_due_reminder_fired": self.pre_due_reminder_fired,
                "due_reminder_fired": self.due_reminder_fired,
                "created_at": serialize_datetime(self.created_at),
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> TaskOccurrence:
        data = require_mapping(value, "occurrence")
        known = {
            "id",
            "template_id",
            "shift_date",
            "title",
            "category",
            "notes",
            "scheduled_time",
            "reminder_enabled",
            "reminder_lead_minutes",
            "sort_order",
            "task_type",
            "shopify_details",
            "status",
            "completed_at",
            "pre_due_reminder_fired",
            "due_reminder_fired",
            "created_at",
        }
        shopify_value = data.get("shopify_details")
        return cls(
            id=require_uuid(data.get("id"), "occurrence.id"),
            template_id=require_uuid(data.get("template_id"), "occurrence.template_id"),
            shift_date=require_date(data.get("shift_date"), "occurrence.shift_date"),
            title=require_string(data.get("title"), "occurrence.title"),
            category=require_string(data.get("category"), "occurrence.category"),
            notes=require_string(
                data.get("notes", ""), "occurrence.notes", allow_blank=True
            ),
            scheduled_time=optional_clock_time(
                data.get("scheduled_time"), "occurrence.scheduled_time"
            ),
            reminder_enabled=require_bool(
                data.get("reminder_enabled", False), "occurrence.reminder_enabled"
            ),
            reminder_lead_minutes=require_int(
                data.get("reminder_lead_minutes", DEFAULT_REMINDER_LEAD_MINUTES),
                "occurrence.reminder_lead_minutes",
                minimum=0,
            ),
            sort_order=require_int(
                data.get("sort_order", 0), "occurrence.sort_order", minimum=0
            ),
            task_type=require_enum(
                data.get("task_type", TaskType.GENERAL.value),
                TaskType,
                "occurrence.task_type",
            ),
            shopify_details=(
                ShopifyDetails.from_dict(shopify_value) if shopify_value is not None else None
            ),
            status=require_enum(
                data.get("status", TaskStatus.PENDING.value),
                TaskStatus,
                "occurrence.status",
            ),
            completed_at=optional_aware_datetime(
                data.get("completed_at"), "occurrence.completed_at"
            ),
            pre_due_reminder_fired=require_bool(
                data.get("pre_due_reminder_fired", False),
                "occurrence.pre_due_reminder_fired",
            ),
            due_reminder_fired=require_bool(
                data.get("due_reminder_fired", False), "occurrence.due_reminder_fired"
            ),
            created_at=require_aware_datetime(
                data.get("created_at"), "occurrence.created_at"
            ),
            extra=collect_extra(data, known),
        )


@dataclass(slots=True)
class TaskDocument:
    """Versioned root document stored in tasks.json."""

    tasks: list[TaskTemplate] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.schema_version = require_int(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(
                f"task document schema must be version {SCHEMA_VERSION} after migration"
            )
        if not isinstance(self.tasks, list) or not all(
            isinstance(task, TaskTemplate) for task in self.tasks
        ):
            raise ModelValidationError("tasks must contain TaskTemplate values")
        identifiers = [task.id for task in self.tasks]
        if len(identifiers) != len(set(identifiers)):
            raise ModelValidationError("tasks contains duplicate task IDs")

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "schema_version": self.schema_version,
                "tasks": [task.to_dict() for task in self.tasks],
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> TaskDocument:
        data = require_mapping(value, "task document")
        items = require_list(data.get("tasks", []), "tasks")
        return cls(
            schema_version=require_int(data.get("schema_version"), "schema_version", minimum=1),
            tasks=[TaskTemplate.from_dict(item) for item in items],
            extra=collect_extra(data, {"schema_version", "tasks"}),
        )
