"""Shared application constants and stable enum values."""

from __future__ import annotations

from enum import StrEnum

APP_NAME = "Shift Checklist"
APP_ID = "shift-checklist"
APP_AUTHOR = "Shift Checklist"
APP_VERSION = "0.1.0-dev"

DEFAULT_RESET_TIME = "12:00"
DEFAULT_CLIENT_CHECK_INTERVAL_MINUTES = 30
DEFAULT_REMINDER_LEAD_MINUTES = 5

DEFAULT_CATEGORIES = (
    "Client Monitoring",
    "FastDTR",
    "Shopify",
    "End of Shift",
    "General",
)


class Recurrence(StrEnum):
    """Supported MVP task recurrence options."""

    DAILY = "daily"
    ONE_TIME = "one_time"


class TaskStatus(StrEnum):
    """Statuses persisted on task occurrences."""

    PENDING = "pending"
    COMPLETED = "completed"
    MISSED = "missed"


class ShopifyStatus(StrEnum):
    """Workflow states for manually entered Shopify work."""

    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    WAITING_FOR_CLARIFICATION = "Waiting for Clarification"
    READY_FOR_REVIEW = "Ready for Review"
    COMPLETED = "Completed"


class Priority(StrEnum):
    """Priority options for conditional Shopify work."""

    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    URGENT = "Urgent"
