"""Fast tests for the application bootstrap layer."""

from pathlib import Path

import pytest

from constants import APP_NAME, APP_VERSION, DEFAULT_CATEGORIES
from main import ShiftChecklistApp, parse_args, resource_root
from services import HistoryService, ServiceContainer, ShiftService, StorageService, TaskService


def test_application_metadata_is_present() -> None:
    assert APP_NAME == "Shift Checklist"
    assert APP_VERSION
    assert len(DEFAULT_CATEGORIES) == len(set(DEFAULT_CATEGORIES))


def test_kv_file_exists_at_resource_root() -> None:
    assert (resource_root() / "shift_checklist.kv").is_file()


def test_application_uses_service_container(tmp_path: Path) -> None:
    app = ShiftChecklistApp(data_directory=tmp_path)
    assert isinstance(app.services, ServiceContainer)
    assert isinstance(app.services.get("storage"), StorageService)
    assert isinstance(app.services.get("shift"), ShiftService)
    assert isinstance(app.services.get("tasks"), TaskService)
    assert isinstance(app.services.get("history"), HistoryService)


def test_service_container_registers_and_returns_a_service() -> None:
    container = ServiceContainer()
    expected = object()

    container.register("example", expected)

    assert container.contains("example")
    assert container.get("example") is expected


@pytest.mark.parametrize("name", ["", " ", "\t"])
def test_service_container_rejects_blank_names(name: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        ServiceContainer().register(name, object())


def test_service_container_rejects_duplicate_names() -> None:
    container = ServiceContainer()
    container.register("example", object())

    with pytest.raises(ValueError, match="already registered"):
        container.register("example", object())


def test_service_container_reports_missing_service() -> None:
    with pytest.raises(LookupError, match="not registered"):
        ServiceContainer().get("missing")


def test_smoke_test_argument_is_opt_in() -> None:
    assert parse_args([]).smoke_test is False
    assert parse_args(["--smoke-test"]).smoke_test is True


def test_data_directory_argument_is_a_path(tmp_path: Path) -> None:
    assert parse_args(["--data-dir", str(tmp_path)]).data_dir == tmp_path


def test_project_root_is_absolute() -> None:
    assert isinstance(resource_root(), Path)
    assert resource_root().is_absolute()
