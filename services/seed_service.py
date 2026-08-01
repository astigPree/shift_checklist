"""First-launch categories and editable default task templates."""

from __future__ import annotations

from datetime import datetime, time

from models import TaskDocument, TaskTemplate
from services.storage_service import StorageService


def _local_now() -> datetime:
    return datetime.now().astimezone()


def create_default_tasks(*, created_at: datetime | None = None) -> list[TaskTemplate]:
    """Return the practical default checklist in stable display order."""

    timestamp = created_at or _local_now()
    task_specs = [
        {
            "title": "Check client messages regularly",
            "category": "Client Monitoring",
            "notes": "Use the Client Messages Checked button after each review.",
        },
        {
            "title": "Review instructions from the boss",
            "category": "Client Monitoring",
        },
        {
            "title": "Record important or pending requests",
            "category": "Client Monitoring",
        },
        {
            "title": "Open FastDTR for JDK checkout",
            "category": "FastDTR",
            "scheduled_time": time(3, 55),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Check out from JDK",
            "category": "FastDTR",
            "scheduled_time": time(4, 0),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Confirm the JDK checkout",
            "category": "FastDTR",
            "scheduled_time": time(4, 2),
        },
        {
            "title": "Check in for Happy BUM",
            "category": "FastDTR",
            "scheduled_time": time(4, 0),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Confirm the Happy BUM check-in",
            "category": "FastDTR",
            "scheduled_time": time(4, 2),
        },
        {
            "title": "Check for Shopify update requests",
            "category": "Shopify",
            "notes": "Create a one-time Shopify task only when work is requested.",
        },
        {
            "title": "Check client messages one final time",
            "category": "End of Shift",
            "scheduled_time": time(7, 45),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Record pending tasks",
            "category": "End of Shift",
            "scheduled_time": time(7, 50),
        },
        {
            "title": "Open FastDTR for Happy BUM checkout",
            "category": "FastDTR",
            "scheduled_time": time(7, 55),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Check out from Happy BUM",
            "category": "FastDTR",
            "scheduled_time": time(8, 0),
            "reminder_enabled": True,
            "reminder_lead_minutes": 0,
        },
        {
            "title": "Confirm the Happy BUM checkout",
            "category": "FastDTR",
            "scheduled_time": time(8, 2),
        },
    ]

    return [
        TaskTemplate(
            **task_spec,
            sort_order=index,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for index, task_spec in enumerate(task_specs)
    ]


def seed_default_tasks(
    storage: StorageService,
    *,
    created_at: datetime | None = None,
) -> bool:
    """Seed defaults once, without overwriting or augmenting an existing list."""

    if not storage.should_seed_default_tasks():
        return False

    document = storage.load_tasks()
    if document.tasks:
        storage.mark_default_tasks_seeded()
        return False

    storage.save_tasks(TaskDocument(tasks=create_default_tasks(created_at=created_at)))
    storage.mark_default_tasks_seeded()
    return True
