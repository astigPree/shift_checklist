"""Resilience, logging, restart persistence, and offline-operation tests."""

from __future__ import annotations

import logging
import socket
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from kivy.app import App
from kivy.base import ExceptionManager
from kivy.uix.popup import Popup

from constants import TimeFormat
from main import ApplicationExceptionHandler, ShiftChecklistApp
from models import TaskTemplate
from services import (
    MessageCheckService,
    SettingsService,
    ShiftService,
    StorageService,
    TaskService,
    close_application_logging,
    configure_logging,
)

MANILA = timezone(timedelta(hours=8))


def test_rotating_application_log_is_written_under_data_directory(
    tmp_path: Path,
) -> None:
    log_path = configure_logging(tmp_path)
    assert log_path == tmp_path / "logs" / "shift-checklist.log"

    logging.getLogger("services.test").warning("Lifecycle verification")
    close_application_logging()

    text = log_path.read_text(encoding="utf-8")
    assert "WARNING | services.test | Lifecycle verification" in text


def test_logging_failure_is_non_fatal_when_data_path_is_not_a_directory(
    tmp_path: Path,
) -> None:
    invalid_data_directory = tmp_path / "blocked"
    invalid_data_directory.write_text("not a directory", encoding="utf-8")

    assert configure_logging(invalid_data_directory) is None


def test_unhandled_exception_is_logged_and_kivy_handler_keeps_app_alive(
    tmp_path: Path,
) -> None:
    app = ShiftChecklistApp(data_directory=tmp_path)
    error = RuntimeError("synthetic callback failure")

    app.report_exception(error, show_dialog=False)
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert app.log_path is not None
    assert "Unhandled application error" in app.log_path.read_text(encoding="utf-8")
    assert ApplicationExceptionHandler(app).handle_exception(error) == ExceptionManager.PASS

    close_application_logging()
    App._running_app = None


def test_abrupt_restart_preserves_every_user_mutation(tmp_path: Path) -> None:
    current = datetime(2026, 8, 1, 20, tzinfo=MANILA)
    storage = StorageService(tmp_path)
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    shift = ShiftService(storage, clock=lambda: current)
    shift.ensure_current_shift()
    tasks = TaskService(storage, shift)
    messages = MessageCheckService(storage, shift, application_started_at=current)
    settings = SettingsService(storage, shift)

    task = tasks.add_task(
        TaskTemplate(
            title="Persist before abrupt exit",
            category="General",
            created_at=current,
            updated_at=current,
        )
    )
    occurrence = shift.ensure_current_shift().occurrences[0]
    tasks.complete_occurrence(occurrence.id, completed_at=current + timedelta(minutes=1))
    messages.record_check("Local restart proof", checked_at=current + timedelta(minutes=2))
    settings.update(time_format=TimeFormat.TWENTY_FOUR_HOUR)

    # Simulate process loss by constructing fresh services without calling any
    # shutdown method on the original objects.
    restarted_storage = StorageService(tmp_path)
    restarted_shift = ShiftService(restarted_storage, clock=lambda: current)
    restarted_tasks = TaskService(restarted_storage, restarted_shift)
    restarted_messages = MessageCheckService(
        restarted_storage,
        restarted_shift,
        application_started_at=current,
    )

    assert restarted_tasks.list_templates()[0].id == task.id
    assert restarted_tasks.list_occurrences()[0].occurrence.completed_at is not None
    assert restarted_messages.latest_for_shift().note == "Local restart proof"
    assert (
        restarted_storage.load_settings().settings.time_format
        is TimeFormat.TWENTY_FOUR_HOUR
    )


def test_representative_normal_workflow_makes_no_network_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    def forbid_socket(*_args: object, **_kwargs: object) -> object:
        attempts.append("socket")
        raise AssertionError("network socket attempted")

    def forbid_url(*_args: object, **_kwargs: object) -> object:
        attempts.append("urlopen")
        raise AssertionError("URL open attempted")

    monkeypatch.setattr(socket, "socket", forbid_socket)
    monkeypatch.setattr(socket, "create_connection", forbid_socket)
    monkeypatch.setattr(urllib.request, "urlopen", forbid_url)
    monkeypatch.setattr(Popup, "open", lambda self, *args: self)
    monkeypatch.setattr(Popup, "dismiss", lambda self, *args: self)

    app = ShiftChecklistApp(data_directory=tmp_path)
    app.root = app.build()
    storage = app.services.get("storage")
    storage.initialize_all()
    storage.mark_default_tasks_seeded()
    shift = app.services.get("shift")
    shift.ensure_current_shift()
    task = app.services.get("tasks").add_task(
        TaskTemplate(
            title="Offline task",
            category="General",
            created_at=shift.now(),
            updated_at=shift.now(),
        )
    )
    occurrence = app.services.get("tasks").list_occurrences()[0].occurrence
    app.services.get("tasks").complete_occurrence(occurrence.id)
    app.services.get("messages").record_check()
    app.services.get("settings").update(notifications_enabled=False)
    app.refresh_screens()
    app.services.get("tasks").delete_task(task.id, confirmed=True)

    assert attempts == []
    close_application_logging()
    App._running_app = None


def test_storage_recovery_notices_are_presented_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = ShiftChecklistApp(data_directory=tmp_path)
    app.root = app.build()
    storage = app.services.get("storage")
    storage.initialize_all()
    storage.save_tasks(storage.load_tasks())
    storage.tasks_path.write_text("not json", encoding="utf-8")
    storage.load_tasks()
    shown: list[tuple[str, str]] = []
    today = app.root.get_screen("today")
    monkeypatch.setattr(
        today,
        "show_message",
        lambda title, message: shown.append((title, message)),
    )

    app._show_storage_notices()
    app._show_storage_notices()

    assert len(shown) == 1
    assert shown[0][0] == "Local data recovered"
    assert "last-known-good backup" in shown[0][1]
    close_application_logging()
    App._running_app = None
