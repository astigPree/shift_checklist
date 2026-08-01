"""Unit tests for safe local JSON persistence."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import services.storage_service as storage_module
from constants import DATA_DIRECTORY_ENV_VAR
from models import TaskDocument, TaskTemplate
from services.storage_service import (
    StorageRecoveryError,
    StorageService,
    StorageWriteError,
    UnsupportedSchemaVersionError,
    resolve_data_directory,
)

NOW = datetime(2026, 8, 1, 20, 0, tzinfo=timezone(timedelta(hours=8)))


def make_task(title: str) -> TaskTemplate:
    return TaskTemplate(
        title=title,
        category="General",
        created_at=NOW,
        updated_at=NOW,
    )


def test_explicit_data_directory_has_highest_priority(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    environment = {DATA_DIRECTORY_ENV_VAR: str(tmp_path / "environment")}

    assert resolve_data_directory(explicit, environment=environment) == explicit.resolve()


def test_environment_can_override_default_data_directory(tmp_path: Path) -> None:
    expected = tmp_path / "environment"

    actual = resolve_data_directory(environment={DATA_DIRECTORY_ENV_VAR: str(expected)})

    assert actual == expected.resolve()


def test_initialize_creates_all_versioned_documents(tmp_path: Path) -> None:
    service = StorageService(tmp_path)

    documents = service.initialize_all()

    assert set(documents) == {"settings", "tasks", "daily_records", "message_checks"}
    for path in (
        service.tasks_path,
        service.daily_records_path,
        service.message_checks_path,
        service.settings_path,
    ):
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_empty_task_list_remains_empty_after_restart(tmp_path: Path) -> None:
    first_service = StorageService(tmp_path)
    first_service.initialize_all()
    first_service.mark_default_tasks_seeded()
    first_service.save_tasks(TaskDocument(tasks=[]))

    second_service = StorageService(tmp_path)

    assert second_service.load_tasks().tasks == []
    assert second_service.should_seed_default_tasks() is False


def test_existing_tasks_without_settings_prevent_accidental_reseed(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    service.tasks_path.write_text(
        json.dumps(TaskDocument(tasks=[]).to_dict()), encoding="utf-8"
    )

    service.initialize_all()

    assert service.should_seed_default_tasks() is False


def test_save_creates_last_known_good_backup(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    first = TaskDocument(tasks=[make_task("First")])
    second = TaskDocument(tasks=[make_task("Second")])

    service.save_tasks(first)
    service.save_tasks(second)

    backup_payload = json.loads(
        service.tasks_path.with_name("tasks.json.bak").read_text(encoding="utf-8")
    )
    assert backup_payload["tasks"][0]["title"] == "First"
    assert service.load_tasks().tasks[0].title == "Second"


def test_corrupt_primary_is_preserved_and_recovered_from_backup(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    service.save_tasks(TaskDocument(tasks=[make_task("Recover me")]))
    service.save_tasks(TaskDocument(tasks=[make_task("Corrupt me")]))
    service.tasks_path.write_text("{ definitely not json", encoding="utf-8")

    recovered = service.load_tasks()
    notices = service.drain_notices()

    assert recovered.tasks[0].title == "Recover me"
    assert json.loads(service.tasks_path.read_text(encoding="utf-8"))["tasks"][0][
        "title"
    ] == "Recover me"
    assert len(notices) == 1
    assert notices[0].corrupt_copy_path is not None
    assert notices[0].corrupt_copy_path.read_text(encoding="utf-8") == "{ definitely not json"


def test_invalid_primary_without_backup_raises_and_preserves_input(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    service.tasks_path.write_text("not json", encoding="utf-8")

    with pytest.raises(StorageRecoveryError, match="no backup"):
        service.load_tasks()

    assert service.tasks_path.read_text(encoding="utf-8") == "not json"
    assert list(tmp_path.glob("tasks.json.corrupt-*"))


def test_invalid_primary_and_backup_raise_recovery_error(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    service.save_tasks(TaskDocument(tasks=[make_task("Create backup")]))
    backup = service.tasks_path.with_name("tasks.json.bak")
    service.tasks_path.write_text("invalid primary", encoding="utf-8")
    backup.write_text("invalid backup", encoding="utf-8")

    with pytest.raises(StorageRecoveryError, match="Both"):
        service.load_tasks()

    assert list(tmp_path.glob("tasks.json.corrupt-*"))
    assert list(tmp_path.glob("tasks.json.bak.corrupt-*"))


def test_missing_primary_is_restored_from_backup(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    service.save_tasks(TaskDocument(tasks=[make_task("Backup value")]))
    service.save_tasks(TaskDocument(tasks=[make_task("Primary value")]))
    service.tasks_path.unlink()

    restored = service.load_tasks()

    assert restored.tasks[0].title == "Backup value"
    assert service.tasks_path.exists()
    assert service.drain_notices()[0].document_name == "tasks"


def test_future_schema_is_rejected_without_overwriting_data(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 99, "tasks": []}
    service.tasks_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnsupportedSchemaVersionError, match="newer schema"):
        service.load_tasks()

    assert json.loads(service.tasks_path.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob("tasks.json.corrupt-*"))


def test_registered_migration_upgrades_legacy_document_and_keeps_backup(
    tmp_path: Path,
) -> None:
    service = StorageService(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy_payload = {"tasks": [], "legacy_note": "keep"}
    service.tasks_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    service.register_migration(
        "tasks",
        0,
        lambda value: {**value, "schema_version": 1},
    )

    migrated = service.load_tasks()

    assert migrated.schema_version == 1
    assert migrated.to_dict()["legacy_note"] == "keep"
    assert json.loads(service.tasks_path.read_text(encoding="utf-8"))["schema_version"] == 1
    backup = json.loads(
        service.tasks_path.with_name("tasks.json.bak").read_text(encoding="utf-8")
    )
    assert "schema_version" not in backup


def test_bad_migration_is_rejected(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    service.tasks_path.write_text(json.dumps({"tasks": []}), encoding="utf-8")
    service.register_migration("tasks", 0, lambda value: value)

    with pytest.raises(StorageRecoveryError, match="no backup"):
        service.load_tasks()


def test_simulated_replace_failure_keeps_previous_primary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    service.save_tasks(TaskDocument(tasks=[make_task("Previous")]))
    original_text = service.tasks_path.read_text(encoding="utf-8")
    real_replace = storage_module.os.replace

    def fail_primary_replace(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == service.tasks_path:
            raise OSError("simulated replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", fail_primary_replace)

    with pytest.raises(StorageWriteError, match="simulated replace failure"):
        service.save_tasks(TaskDocument(tasks=[make_task("New")]))

    assert service.tasks_path.read_text(encoding="utf-8") == original_text
    assert not list(tmp_path.glob("*.tmp"))


def test_save_revalidates_mutated_documents(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    document = TaskDocument(tasks=[make_task("Valid")])
    document.tasks[0].title = " "

    with pytest.raises(StorageWriteError, match="cannot be blank"):
        service.save_tasks(document)


def test_unicode_content_round_trips_as_utf8(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.save_tasks(TaskDocument(tasks=[make_task("Review café request ✓")]))

    assert service.load_tasks().tasks[0].title == "Review café request ✓"
    assert "café" in service.tasks_path.read_text(encoding="utf-8")


def test_concurrent_saves_remain_parseable(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()

    def save_document(index: int) -> None:
        service.save_tasks(TaskDocument(tasks=[make_task(f"Task {index}")]))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_document, range(24)))

    loaded = service.load_tasks()
    assert loaded.tasks[0].title.startswith("Task ")
    assert not list(tmp_path.glob("*.tmp"))


def test_health_check_reports_document_status_without_repair(tmp_path: Path) -> None:
    service = StorageService(tmp_path)
    service.initialize_all()
    service.message_checks_path.write_text("invalid", encoding="utf-8")

    health = service.health_check()

    assert health.writable is True
    assert health.documents["tasks"] == "ok"
    assert health.documents["message_checks"] == "invalid"
    assert service.message_checks_path.read_text(encoding="utf-8") == "invalid"
