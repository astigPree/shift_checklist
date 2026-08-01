"""Thread-safe, versioned, and recoverable JSON persistence."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, TypeVar, cast
from uuid import uuid4

from platformdirs import PlatformDirs

from constants import APP_NAME, DATA_DIRECTORY_ENV_VAR, SCHEMA_VERSION
from models import (
    DailyRecordsDocument,
    MessageChecksDocument,
    ModelValidationError,
    SettingsDocument,
    TaskDocument,
)

LOGGER = logging.getLogger(__name__)
DATA_APP_NAME = APP_NAME.replace(" ", "")


class PersistedDocument(Protocol):
    """Structural type implemented by each versioned root document."""

    schema_version: int

    def to_dict(self) -> dict[str, Any]: ...


DocumentType = TypeVar("DocumentType", bound=PersistedDocument)
DocumentParser = Callable[[Any], PersistedDocument]
DocumentFactory = Callable[[], PersistedDocument]
Migration = Callable[[dict[str, Any]], dict[str, Any]]


class StorageError(RuntimeError):
    """Base exception for persistence failures."""


class StorageReadError(StorageError):
    """Raised when a document cannot be read from disk."""


class StorageWriteError(StorageError):
    """Raised when an atomic write cannot be completed."""


class StorageRecoveryError(StorageError):
    """Raised when invalid primary data has no usable backup."""


class UnsupportedSchemaVersionError(StorageError):
    """Raised when no safe migration path exists for a document."""


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    """Parser and filename metadata for one JSON root document."""

    name: str
    filename: str
    parser: DocumentParser
    default_factory: DocumentFactory


@dataclass(frozen=True, slots=True)
class StorageNotice:
    """User-displayable, non-sensitive information about a recovery action."""

    document_name: str
    message: str
    corrupt_copy_path: Path | None = None


@dataclass(frozen=True, slots=True)
class StorageHealth:
    """Read-only storage health summary."""

    data_directory: Path
    writable: bool
    documents: dict[str, str]


def resolve_data_directory(
    explicit_path: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve explicit, environment, or Windows per-user application storage."""

    if explicit_path is not None:
        return Path(explicit_path).expanduser().resolve()

    env = os.environ if environment is None else environment
    environment_value = env.get(DATA_DIRECTORY_ENV_VAR, "").strip()
    if environment_value:
        return Path(environment_value).expanduser().resolve()

    user_data = PlatformDirs(DATA_APP_NAME, appauthor=False, roaming=False).user_data_path
    return (user_data / "data").resolve()


class StorageService:
    """Load and save all application documents behind one re-entrant lock."""

    def __init__(self, data_directory: str | Path | None = None) -> None:
        self.data_directory = resolve_data_directory(data_directory)
        self._lock = RLock()
        self._notices: list[StorageNotice] = []
        self._migrations: dict[tuple[str, int], Migration] = {}
        self._specs = {
            "tasks": DocumentSpec(
                "tasks", "tasks.json", TaskDocument.from_dict, TaskDocument
            ),
            "daily_records": DocumentSpec(
                "daily_records",
                "daily_records.json",
                DailyRecordsDocument.from_dict,
                DailyRecordsDocument,
            ),
            "message_checks": DocumentSpec(
                "message_checks",
                "message_checks.json",
                MessageChecksDocument.from_dict,
                MessageChecksDocument,
            ),
            "settings": DocumentSpec(
                "settings", "settings.json", SettingsDocument.from_dict, SettingsDocument
            ),
        }

    @property
    def tasks_path(self) -> Path:
        return self._path_for("tasks")

    @property
    def daily_records_path(self) -> Path:
        return self._path_for("daily_records")

    @property
    def message_checks_path(self) -> Path:
        return self._path_for("message_checks")

    @property
    def settings_path(self) -> Path:
        return self._path_for("settings")

    def register_migration(
        self, document_name: str, from_version: int, migration: Migration
    ) -> None:
        """Register one sequential schema migration hook."""

        if document_name not in self._specs:
            raise ValueError(f"unknown document name: {document_name}")
        if isinstance(from_version, bool) or not isinstance(from_version, int):
            raise ValueError("from_version must be an integer")
        if from_version < 0 or from_version >= SCHEMA_VERSION:
            raise ValueError(f"from_version must be between 0 and {SCHEMA_VERSION - 1}")
        if not callable(migration):
            raise TypeError("migration must be callable")
        key = (document_name, from_version)
        if key in self._migrations:
            raise ValueError(
                f"migration already registered for {document_name} version {from_version}"
            )
        self._migrations[key] = migration

    def initialize_all(self) -> dict[str, PersistedDocument]:
        """Create/load every root document and preserve seed-once state."""

        with self._lock:
            tasks_existed = self.tasks_path.exists() or self._backup_path(
                self.tasks_path
            ).exists()
            settings_existed = self.settings_path.exists() or self._backup_path(
                self.settings_path
            ).exists()

            settings = self.load_settings()
            if tasks_existed and not settings_existed and not settings.settings.default_tasks_seeded:
                settings.settings.default_tasks_seeded = True
                self.save_settings(settings)

            return {
                "settings": settings,
                "tasks": self.load_tasks(),
                "daily_records": self.load_daily_records(),
                "message_checks": self.load_message_checks(),
            }

    def load_tasks(self) -> TaskDocument:
        return cast(TaskDocument, self._load("tasks"))

    def save_tasks(self, document: TaskDocument) -> None:
        self._save("tasks", document)

    def load_daily_records(self) -> DailyRecordsDocument:
        return cast(DailyRecordsDocument, self._load("daily_records"))

    def save_daily_records(self, document: DailyRecordsDocument) -> None:
        self._save("daily_records", document)

    def load_message_checks(self) -> MessageChecksDocument:
        return cast(MessageChecksDocument, self._load("message_checks"))

    def save_message_checks(self, document: MessageChecksDocument) -> None:
        self._save("message_checks", document)

    def load_settings(self) -> SettingsDocument:
        return cast(SettingsDocument, self._load("settings"))

    def save_settings(self, document: SettingsDocument) -> None:
        self._save("settings", document)

    def should_seed_default_tasks(self) -> bool:
        """Return whether first-launch defaults have never been seeded."""

        return not self.load_settings().settings.default_tasks_seeded

    def mark_default_tasks_seeded(self) -> None:
        """Persist the seed-once marker without altering the task list."""

        with self._lock:
            document = self.load_settings()
            if not document.settings.default_tasks_seeded:
                document.settings.default_tasks_seeded = True
                self.save_settings(document)

    def drain_notices(self) -> list[StorageNotice]:
        """Return and clear recovery notices for later UI display."""

        with self._lock:
            notices = list(self._notices)
            self._notices.clear()
            return notices

    def health_check(self) -> StorageHealth:
        """Check writability and parse documents without repairing or modifying them."""

        with self._lock:
            writable = self._check_writable()
            statuses: dict[str, str] = {}
            for name, spec in self._specs.items():
                path = self._path_for(name)
                if not path.exists():
                    statuses[name] = "missing"
                    continue
                try:
                    self._read_document(path, spec)
                except UnsupportedSchemaVersionError:
                    statuses[name] = "unsupported_schema"
                except (OSError, UnicodeError, json.JSONDecodeError, ModelValidationError):
                    statuses[name] = "invalid"
                else:
                    statuses[name] = "ok"
            return StorageHealth(self.data_directory, writable, statuses)

    def _path_for(self, document_name: str) -> Path:
        try:
            filename = self._specs[document_name].filename
        except KeyError as error:
            raise ValueError(f"unknown document name: {document_name}") from error
        return self.data_directory / filename

    @staticmethod
    def _backup_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.bak")

    def _load(self, document_name: str) -> PersistedDocument:
        with self._lock:
            spec = self._specs[document_name]
            path = self._path_for(document_name)
            backup_path = self._backup_path(path)
            self._ensure_directory()

            if not path.exists():
                if backup_path.exists():
                    return self._recover_missing_primary(spec, path, backup_path)
                document = spec.default_factory()
                self._write_validated(spec, path, document, create_backup=False)
                LOGGER.info("Created missing %s document", spec.name)
                return document

            try:
                document, migrated = self._read_document(path, spec)
            except UnsupportedSchemaVersionError:
                raise
            except OSError as error:
                raise StorageReadError(f"Could not read {path}: {error}") from error
            except (UnicodeError, json.JSONDecodeError, ModelValidationError) as error:
                return self._recover_invalid_primary(spec, path, backup_path, error)

            if migrated:
                self._write_validated(spec, path, document, create_backup=True)
                LOGGER.info("Migrated %s to schema version %s", spec.name, SCHEMA_VERSION)
            return document

    def _save(self, document_name: str, document: PersistedDocument) -> None:
        with self._lock:
            spec = self._specs[document_name]
            path = self._path_for(document_name)
            self._ensure_directory()
            self._write_validated(spec, path, document, create_backup=path.exists())
            LOGGER.debug("Saved %s document", spec.name)

    def _write_validated(
        self,
        spec: DocumentSpec,
        path: Path,
        document: PersistedDocument,
        *,
        create_backup: bool,
    ) -> None:
        try:
            validated = spec.parser(document.to_dict())
            encoded = json.dumps(
                validated.to_dict(),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            ) + "\n"
        except (AttributeError, TypeError, ValueError, ModelValidationError) as error:
            raise StorageWriteError(f"Invalid {spec.name} document: {error}") from error
        self._atomic_write(path, encoded, create_backup=create_backup)

    def _atomic_write(self, path: Path, text: str, *, create_backup: bool) -> None:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f"{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())

            if create_backup and path.exists():
                self._atomic_copy(path, self._backup_path(path))
            os.replace(temp_path, path)
            temp_path = None
        except OSError as error:
            raise StorageWriteError(f"Could not atomically write {path}: {error}") from error
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Could not remove temporary storage file %s", temp_path)

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        temp_destination = destination.with_name(
            f"{destination.name}.{uuid4().hex}.tmp"
        )
        try:
            with source.open("rb") as source_handle, temp_destination.open("xb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)
                target_handle.flush()
                os.fsync(target_handle.fileno())
            os.replace(temp_destination, destination)
        finally:
            try:
                temp_destination.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove temporary backup file %s", temp_destination)

    def _read_document(
        self, path: Path, spec: DocumentSpec
    ) -> tuple[PersistedDocument, bool]:
        raw_text = path.read_text(encoding="utf-8")
        raw_value = json.loads(raw_text)
        if not isinstance(raw_value, dict):
            raise ModelValidationError(f"{spec.name} root must be a JSON object")
        migrated_value, migrated = self._apply_migrations(spec.name, raw_value)
        return spec.parser(migrated_value), migrated

    def _apply_migrations(
        self, document_name: str, value: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        raw_version = value.get("schema_version", 0)
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise ModelValidationError("schema_version must be an integer")
        if raw_version > SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"{document_name} uses newer schema version {raw_version}; "
                f"this app supports {SCHEMA_VERSION}"
            )
        if raw_version < 0:
            raise UnsupportedSchemaVersionError(
                f"{document_name} has invalid schema version {raw_version}"
            )

        current_value = value
        current_version = raw_version
        migrated = False
        while current_version < SCHEMA_VERSION:
            migration = self._migrations.get((document_name, current_version))
            if migration is None:
                raise UnsupportedSchemaVersionError(
                    f"No migration registered for {document_name} schema "
                    f"version {current_version}"
                )
            migrated_value = migration(dict(current_value))
            if not isinstance(migrated_value, dict):
                raise ModelValidationError("migration must return a JSON object")
            next_version = migrated_value.get("schema_version")
            if next_version != current_version + 1:
                raise ModelValidationError(
                    "migration must increase schema_version by exactly one"
                )
            current_value = migrated_value
            current_version = next_version
            migrated = True
        return current_value, migrated

    def _recover_missing_primary(
        self, spec: DocumentSpec, path: Path, backup_path: Path
    ) -> PersistedDocument:
        try:
            document, _migrated = self._read_document(backup_path, spec)
        except UnsupportedSchemaVersionError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ModelValidationError) as error:
            raise StorageRecoveryError(
                f"{spec.name} primary is missing and backup is unusable: {error}"
            ) from error
        self._write_validated(spec, path, document, create_backup=False)
        notice = StorageNotice(spec.name, f"Restored missing {path.name} from backup")
        self._notices.append(notice)
        LOGGER.warning(notice.message)
        return document

    def _recover_invalid_primary(
        self,
        spec: DocumentSpec,
        path: Path,
        backup_path: Path,
        primary_error: Exception,
    ) -> PersistedDocument:
        corrupt_copy = self._preserve_corrupt_file(path)
        if not backup_path.exists():
            raise StorageRecoveryError(
                f"{path.name} is invalid and no backup exists; original preserved at "
                f"{corrupt_copy or path}: {primary_error}"
            ) from primary_error
        try:
            document, _migrated = self._read_document(backup_path, spec)
        except UnsupportedSchemaVersionError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ModelValidationError) as backup_error:
            backup_copy = self._preserve_corrupt_file(backup_path)
            raise StorageRecoveryError(
                f"Both {path.name} and its backup are invalid; preserved copies: "
                f"{corrupt_copy or path}, {backup_copy or backup_path}"
            ) from backup_error

        if corrupt_copy is not None:
            self._write_validated(spec, path, document, create_backup=False)
        notice = StorageNotice(
            spec.name,
            f"Recovered {path.name} from its last-known-good backup",
            corrupt_copy,
        )
        self._notices.append(notice)
        LOGGER.warning("%s; primary error: %s", notice.message, primary_error)
        return document

    @staticmethod
    def _preserve_corrupt_file(path: Path) -> Path | None:
        destination = path.with_name(f"{path.name}.corrupt-{uuid4().hex}")
        try:
            shutil.copy2(path, destination)
        except OSError:
            LOGGER.exception("Could not preserve invalid storage file %s", path)
            return None
        return destination

    def _ensure_directory(self) -> None:
        try:
            self.data_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StorageWriteError(
                f"Could not create data directory {self.data_directory}: {error}"
            ) from error

    def _check_writable(self) -> bool:
        try:
            self._ensure_directory()
            with tempfile.NamedTemporaryFile(dir=self.data_directory, delete=True):
                pass
        except (OSError, StorageWriteError):
            return False
        return True
