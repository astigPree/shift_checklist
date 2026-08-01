"""Validated application settings and their versioned root document."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from typing import Any

from constants import (
    APP_VERSION,
    DEFAULT_CATEGORIES,
    DEFAULT_CLIENT_CHECK_INTERVAL_MINUTES,
    DEFAULT_REMINDER_LEAD_MINUTES,
    DEFAULT_RESET_TIME,
    SCHEMA_VERSION,
    TimeFormat,
)
from models.validation import (
    ModelValidationError,
    collect_extra,
    merge_extra,
    optional_string,
    require_bool,
    require_clock_time,
    require_enum,
    require_int,
    require_list,
    require_mapping,
    require_string,
    serialize_clock_time,
)


@dataclass(slots=True)
class AppSettings:
    """MVP settings with safe defaults for omitted fields."""

    notifications_enabled: bool = True
    sound_enabled: bool = True
    reminder_sound_path: str | None = None
    client_check_interval_minutes: int = DEFAULT_CLIENT_CHECK_INTERVAL_MINUTES
    default_reminder_lead_minutes: int = DEFAULT_REMINDER_LEAD_MINUTES
    reset_time: time = field(default_factory=lambda: require_clock_time(DEFAULT_RESET_TIME, "reset_time"))
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    time_format: TimeFormat = TimeFormat.TWELVE_HOUR
    last_opened_app_version: str = APP_VERSION
    default_tasks_seeded: bool = False
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.notifications_enabled = require_bool(
            self.notifications_enabled, "settings.notifications_enabled"
        )
        self.sound_enabled = require_bool(self.sound_enabled, "settings.sound_enabled")
        self.reminder_sound_path = optional_string(
            self.reminder_sound_path, "settings.reminder_sound_path"
        )
        self.client_check_interval_minutes = require_int(
            self.client_check_interval_minutes,
            "settings.client_check_interval_minutes",
            minimum=1,
        )
        self.default_reminder_lead_minutes = require_int(
            self.default_reminder_lead_minutes,
            "settings.default_reminder_lead_minutes",
            minimum=0,
        )
        self.reset_time = require_clock_time(self.reset_time, "settings.reset_time")
        if not isinstance(self.categories, list):
            raise ModelValidationError("settings.categories must be a list")
        self.categories = [
            require_string(category, f"settings.categories[{index}]")
            for index, category in enumerate(self.categories)
        ]
        if not self.categories:
            raise ModelValidationError("settings.categories cannot be empty")
        normalized = [category.casefold() for category in self.categories]
        if len(normalized) != len(set(normalized)):
            raise ModelValidationError("settings.categories must be unique")
        self.time_format = require_enum(
            self.time_format, TimeFormat, "settings.time_format"
        )
        self.last_opened_app_version = require_string(
            self.last_opened_app_version, "settings.last_opened_app_version"
        )
        self.default_tasks_seeded = require_bool(
            self.default_tasks_seeded, "settings.default_tasks_seeded"
        )

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "notifications_enabled": self.notifications_enabled,
                "sound_enabled": self.sound_enabled,
                "reminder_sound_path": self.reminder_sound_path,
                "client_check_interval_minutes": self.client_check_interval_minutes,
                "default_reminder_lead_minutes": self.default_reminder_lead_minutes,
                "reset_time": serialize_clock_time(self.reset_time),
                "categories": list(self.categories),
                "time_format": self.time_format.value,
                "last_opened_app_version": self.last_opened_app_version,
                "default_tasks_seeded": self.default_tasks_seeded,
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> AppSettings:
        data = require_mapping(value, "settings")
        category_values = require_list(
            data.get("categories", list(DEFAULT_CATEGORIES)), "settings.categories"
        )
        known = {
            "notifications_enabled",
            "sound_enabled",
            "reminder_sound_path",
            "client_check_interval_minutes",
            "default_reminder_lead_minutes",
            "reset_time",
            "categories",
            "time_format",
            "last_opened_app_version",
            "default_tasks_seeded",
        }
        return cls(
            notifications_enabled=require_bool(
                data.get("notifications_enabled", True), "settings.notifications_enabled"
            ),
            sound_enabled=require_bool(
                data.get("sound_enabled", True), "settings.sound_enabled"
            ),
            reminder_sound_path=optional_string(
                data.get("reminder_sound_path"), "settings.reminder_sound_path"
            ),
            client_check_interval_minutes=require_int(
                data.get(
                    "client_check_interval_minutes",
                    DEFAULT_CLIENT_CHECK_INTERVAL_MINUTES,
                ),
                "settings.client_check_interval_minutes",
                minimum=1,
            ),
            default_reminder_lead_minutes=require_int(
                data.get(
                    "default_reminder_lead_minutes",
                    DEFAULT_REMINDER_LEAD_MINUTES,
                ),
                "settings.default_reminder_lead_minutes",
                minimum=0,
            ),
            reset_time=require_clock_time(
                data.get("reset_time", DEFAULT_RESET_TIME), "settings.reset_time"
            ),
            categories=[
                require_string(category, f"settings.categories[{index}]")
                for index, category in enumerate(category_values)
            ],
            time_format=require_enum(
                data.get("time_format", TimeFormat.TWELVE_HOUR.value),
                TimeFormat,
                "settings.time_format",
            ),
            last_opened_app_version=require_string(
                data.get("last_opened_app_version", APP_VERSION),
                "settings.last_opened_app_version",
            ),
            default_tasks_seeded=require_bool(
                data.get("default_tasks_seeded", False),
                "settings.default_tasks_seeded",
            ),
            extra=collect_extra(data, known),
        )


@dataclass(slots=True)
class SettingsDocument:
    """Versioned root document stored in settings.json."""

    settings: AppSettings = field(default_factory=AppSettings)
    schema_version: int = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.schema_version = require_int(self.schema_version, "schema_version", minimum=1)
        if self.schema_version != SCHEMA_VERSION:
            raise ModelValidationError(
                f"settings schema must be version {SCHEMA_VERSION} after migration"
            )
        if not isinstance(self.settings, AppSettings):
            raise ModelValidationError("settings must contain an AppSettings value")

    def to_dict(self) -> dict[str, Any]:
        return merge_extra(
            self.extra,
            {
                "schema_version": self.schema_version,
                "settings": self.settings.to_dict(),
            },
        )

    @classmethod
    def from_dict(cls, value: Any) -> SettingsDocument:
        data = require_mapping(value, "settings document")
        return cls(
            schema_version=require_int(data.get("schema_version"), "schema_version", minimum=1),
            settings=AppSettings.from_dict(data.get("settings", {})),
            extra=collect_extra(data, {"schema_version", "settings"}),
        )
