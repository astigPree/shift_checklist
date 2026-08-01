"""Application services and dependency container."""

from services.app_state import ServiceContainer
from services.history_service import (
    DailySummary,
    HistoryNotFoundError,
    HistoryService,
    ShiftHistoryDetail,
)
from services.message_check_service import MessageCheckService
from services.reminder_service import (
    KivySoundBackend,
    PlyerNotificationBackend,
    ReminderEvent,
    ReminderKind,
    ReminderService,
)
from services.seed_service import create_default_tasks, seed_default_tasks
from services.settings_service import (
    CategoryInUseError,
    ResetTimeConfirmationRequired,
    SettingsService,
    UnsafeResetTimeChange,
)
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
    "CategoryInUseError",
    "ConfirmationRequiredError",
    "DailySummary",
    "HistoryNotFoundError",
    "HistoryService",
    "KivySoundBackend",
    "MessageCheckService",
    "OccurrenceView",
    "PlyerNotificationBackend",
    "ReminderEvent",
    "ReminderKind",
    "ReminderService",
    "ResetTimeConfirmationRequired",
    "ShiftHistoryDetail",
    "ShiftService",
    "ShiftStateError",
    "StorageError",
    "StorageHealth",
    "StorageNotice",
    "StorageRecoveryError",
    "StorageService",
    "SettingsService",
    "TaskNotFoundError",
    "TaskService",
    "UnsafeResetTimeChange",
    "UnsupportedSchemaVersionError",
    "resolve_data_directory",
    "active_shift_date",
    "create_default_tasks",
    "scheduled_datetime",
    "seed_default_tasks",
    "shift_end",
    "shift_start",
)
