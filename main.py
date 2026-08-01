"""Shift Checklist desktop application entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

# Kivy normally consumes command-line arguments during import. The application
# owns its arguments so smoke tests and future data-directory overrides are safe.
os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.uix.screenmanager import ScreenManager

import screens  # noqa: F401 - imports register screen classes for the KV loader
import widgets  # noqa: F401 - imports register reusable widgets for the KV loader
from constants import APP_NAME, APP_VERSION
from models import TaskDocument, TaskTemplate
from services import (
    HistoryService,
    MessageCheckService,
    ReminderService,
    ServiceContainer,
    SettingsService,
    ShiftService,
    StorageService,
    TaskService,
    close_application_logging,
    configure_logging,
    seed_default_tasks,
)

PROJECT_ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
SMOKE_DATASETS = ("empty", "typical", "large")
LARGE_SMOKE_TASK_COUNT = 200


@dataclass(frozen=True, slots=True)
class BannerMessage:
    """Small presentation value accepted by the Today reminder banner."""

    title: str
    message: str


class ApplicationExceptionHandler(ExceptionHandler):
    """Keep a recoverable Kivy callback failure from closing the whole app."""

    def __init__(self, app: ShiftChecklistApp) -> None:
        self.app = app

    def handle_exception(self, exception: Exception) -> int:
        self.app.report_exception(exception)
        return ExceptionManager.PASS


def resource_root() -> Path:
    """Return the source or PyInstaller extraction directory."""

    bundled_root = getattr(sys, "_MEIPASS", None)
    return Path(bundled_root) if bundled_root else PROJECT_ROOT


class ShiftChecklistApp(App):
    """Kivy application shell shared by all screens."""

    title = APP_NAME

    def __init__(
        self,
        *,
        smoke_test: bool = False,
        smoke_dataset: str = "typical",
        data_directory: Path | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        if smoke_dataset not in SMOKE_DATASETS:
            raise ValueError(f"unknown smoke-test dataset: {smoke_dataset}")
        self.smoke_test = smoke_test
        self.smoke_dataset = smoke_dataset
        self._shift_rollover_event = None
        self._reminder_poll_event = None
        self._exception_handler = ApplicationExceptionHandler(self)
        self._exception_handler_registered = False
        self._exception_dialog_pending = False
        self._shutdown_complete = False
        self.services = ServiceContainer()
        storage = StorageService(data_directory)
        self.log_path = configure_logging(storage.data_directory)
        shift_service = ShiftService(storage)
        message_service = MessageCheckService(storage, shift_service)
        settings_service = SettingsService(storage, shift_service)
        self.services.register("storage", storage)
        self.services.register("shift", shift_service)
        self.services.register("tasks", TaskService(storage, shift_service))
        self.services.register("history", HistoryService(storage))
        self.services.register("messages", message_service)
        self.services.register("settings", settings_service)
        self.services.register(
            "reminders",
            ReminderService(storage, shift_service, message_service),
        )
        settings_service.subscribe(self._settings_changed)

    def build(self) -> ScreenManager:
        """Load the KV layout and return the root screen manager."""

        Window.size = (1100, 720)
        root_path = resource_root()
        resource_add_path(str(root_path))
        icon_path = root_path / "assets" / "icons" / "shift-checklist.png"
        if icon_path.is_file():
            Window.set_icon(str(icon_path))
        root = Builder.load_file(str(root_path / "shift_checklist.kv"))
        if not isinstance(root, ScreenManager):
            raise TypeError("shift_checklist.kv must define a ScreenManager root")
        return root

    def on_start(self) -> None:
        """Initialize local documents and optionally stop after smoke validation."""

        ExceptionManager.add_handler(self._exception_handler)
        self._exception_handler_registered = True
        storage = self.services.get("storage")
        storage.initialize_all()
        if self.smoke_test:
            self._prepare_smoke_dataset()
        seed_default_tasks(storage, created_at=self.services.get("shift").now())
        self.services.get("shift").ensure_current_shift()
        self.reschedule_shift_boundary()
        today = self.root.get_screen("today")
        self.services.get("reminders").subscribe_banner(today.show_banner)
        self._reminder_poll_event = Clock.schedule_interval(self._poll_reminders, 15)
        self.refresh_screens()
        self._poll_reminders(0)
        self._show_storage_notices()
        LOGGER.info("Application started (version=%s)", APP_VERSION)
        if self.smoke_test:
            self._schedule_smoke_navigation()

    def _prepare_smoke_dataset(self) -> None:
        """Create a deterministic empty/typical/large dataset only for smoke mode."""

        storage = self.services.get("storage")
        if self.smoke_dataset == "typical":
            return
        storage.mark_default_tasks_seeded()
        if self.smoke_dataset == "empty":
            storage.save_tasks(TaskDocument(tasks=[]))
            return
        now = self.services.get("shift").now()
        storage.save_tasks(
            TaskDocument(
                tasks=[
                    TaskTemplate(
                        title=f"Large dataset task {index + 1:03d}",
                        category="General",
                        sort_order=index,
                        created_at=now,
                        updated_at=now,
                    )
                    for index in range(LARGE_SMOKE_TASK_COUNT)
                ]
            )
        )

    def _show_storage_notices(self) -> None:
        notices = self.services.get("storage").drain_notices()
        if not notices or self.root is None:
            return
        for notice in notices:
            LOGGER.warning("Storage recovery: %s", notice.message)
        self.root.get_screen("today").show_message(
            "Local data recovered",
            "\n".join(notice.message for notice in notices),
        )

    def refresh_screens(self) -> None:
        """Ask every built screen to reflect the latest persisted state."""

        if self.root is None:
            return
        for screen in self.root.screens:
            refresh = getattr(screen, "refresh", None)
            if callable(refresh):
                refresh()

    def _settings_changed(self) -> None:
        """Apply saved timing changes immediately across the running app."""

        self.reschedule_shift_boundary()
        self.refresh_screens()

    def _poll_reminders(self, _elapsed: float) -> None:
        """Evaluate reminders on the Kivy event loop without blocking the UI."""

        try:
            events = self.services.get("reminders").poll()
            if events:
                self.refresh_screens()
        except Exception as error:
            LOGGER.exception("Reminder polling failed")
            if self.root is not None:
                self.root.get_screen("today").show_banner(
                    BannerMessage("Reminder check failed", str(error))
                )

    def report_exception(self, error: Exception, *, show_dialog: bool = True) -> None:
        """Log an unexpected failure and show one non-recursive readable dialog."""

        LOGGER.error(
            "Unhandled application error",
            exc_info=(type(error), error, error.__traceback__),
        )
        if not show_dialog or self.root is None or self._exception_dialog_pending:
            return
        self._exception_dialog_pending = True
        Clock.schedule_once(self._show_exception_dialog, 0)

    def _show_exception_dialog(self, _elapsed: float) -> None:
        try:
            destination = str(self.log_path) if self.log_path else "the Kivy diagnostic log"
            self.root.get_screen("today").show_message(
                "Unexpected application error",
                "The current action could not be completed. Previously saved data is "
                f"unchanged. Technical details were written to {destination}.",
            )
        except Exception:
            LOGGER.exception("Could not display the application error dialog")
        finally:
            self._exception_dialog_pending = False

    def _schedule_smoke_navigation(self) -> None:
        """Exercise every screen before a smoke-test process exits."""

        step_delay = 0.3 if self.smoke_dataset == "large" else 0.12
        for delay, screen_name in enumerate(("tasks", "history", "settings", "today"), 1):
            Clock.schedule_once(
                lambda _elapsed, name=screen_name: setattr(self.root, "current", name),
                delay * step_delay,
            )
        Clock.schedule_once(lambda _elapsed: self.stop(), step_delay * 5.5)

    def reschedule_shift_boundary(self) -> None:
        """Schedule exactly one callback at the currently configured reset boundary."""

        if self._shift_rollover_event is not None:
            self._shift_rollover_event.cancel()
        delay = max(0.1, self.services.get("shift").seconds_until_next_boundary())
        self._shift_rollover_event = Clock.schedule_once(self._rollover_shift, delay)

    def _rollover_shift(self, _elapsed: float) -> None:
        """Finalize/open records at the boundary and schedule the next one."""

        self.services.get("shift").ensure_current_shift()
        self.refresh_screens()
        self._poll_reminders(0)
        self.reschedule_shift_boundary()

    def on_stop(self) -> None:
        """Cancel scheduled callbacks cleanly before the application exits."""

        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        if self._shift_rollover_event is not None:
            self._shift_rollover_event.cancel()
            self._shift_rollover_event = None
        if self._reminder_poll_event is not None:
            self._reminder_poll_event.cancel()
            self._reminder_poll_event = None
        self.services.get("settings").unsubscribe(self._settings_changed)
        if self.root is not None:
            self.services.get("reminders").unsubscribe_banner(
                self.root.get_screen("today").show_banner
            )
        if self._exception_handler_registered:
            ExceptionManager.remove_handler(self._exception_handler)
            self._exception_handler_registered = False
        LOGGER.info("Application stopped cleanly")
        close_application_logging()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse Shift Checklist command-line options."""

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="open the Kivy window briefly, then exit successfully",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="override the local data directory for development or testing",
    )
    parser.add_argument(
        "--smoke-dataset",
        choices=SMOKE_DATASETS,
        default="typical",
        help="dataset size used with --smoke-test (default: typical)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application and return a process exit code."""

    args = parse_args(argv)
    if args.smoke_test and args.data_dir is None:
        with TemporaryDirectory(prefix="shift-checklist-smoke-") as temporary_directory:
            app = ShiftChecklistApp(
                smoke_test=True,
                smoke_dataset=args.smoke_dataset,
                data_directory=Path(temporary_directory),
            )
            return run_application(app)
    else:
        app = ShiftChecklistApp(
            smoke_test=args.smoke_test,
            smoke_dataset=args.smoke_dataset,
            data_directory=args.data_dir,
        )
        return run_application(app)


def run_application(app: ShiftChecklistApp) -> int:
    """Run with a final exception boundary that also covers startup failures."""

    try:
        app.run()
    except Exception as error:
        app.report_exception(error, show_dialog=False)
        app.on_stop()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
