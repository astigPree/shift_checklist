"""Application services and dependency container."""

from services.app_state import ServiceContainer
from services.history_service import (
    DailySummary,
    HistoryNotFoundError,
    HistoryService,
    ShiftHistoryDetail,
)
from services.seed_service import create_default_tasks, seed_default_tasks
from services.shift_service import (
    ShiftService,
    ShiftStateError,
    active_shift_date,
    scheduled_datetime,
    shift_end,
    shift_start,
)
from services.storage_service import (
    StorageError,
    StorageHealth,
    StorageNotice,
    StorageRecoveryError,
    StorageService,
    UnsupportedSchemaVersionError,
    resolve_data_directory,
)
from services.task_service import (
    CategoryNotFoundError,
    ConfirmationRequiredError,
    OccurrenceView,
    TaskNotFoundError,
    TaskService,
)

__all__ = (
    "ServiceContainer",
    "CategoryNotFoundError",
    "ConfirmationRequiredError",
    "DailySummary",
    "HistoryNotFoundError",
    "HistoryService",
    "OccurrenceView",
    "ShiftHistoryDetail",
    "ShiftService",
    "ShiftStateError",
    "StorageError",
    "StorageHealth",
    "StorageNotice",
    "StorageRecoveryError",
    "StorageService",
    "TaskNotFoundError",
    "TaskService",
    "UnsupportedSchemaVersionError",
    "resolve_data_directory",
    "active_shift_date",
    "create_default_tasks",
    "scheduled_datetime",
    "seed_default_tasks",
    "shift_end",
    "shift_start",
)
