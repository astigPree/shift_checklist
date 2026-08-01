"""Shift Checklist desktop application entry point."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

# Kivy normally consumes command-line arguments during import. The application
# owns its arguments so smoke tests and future data-directory overrides are safe.
os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.resources import resource_add_path
from kivy.uix.screenmanager import ScreenManager

import screens  # noqa: F401 - imports register screen classes for the KV loader
from constants import APP_NAME, APP_VERSION
from services import ServiceContainer, StorageService

PROJECT_ROOT = Path(__file__).resolve().parent


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
        data_directory: Path | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.smoke_test = smoke_test
        self.services = ServiceContainer()
        self.services.register("storage", StorageService(data_directory))

    def build(self) -> ScreenManager:
        """Load the KV layout and return the root screen manager."""

        Window.size = (1100, 720)
        root_path = resource_root()
        resource_add_path(str(root_path))
        root = Builder.load_file(str(root_path / "shift_checklist.kv"))
        if not isinstance(root, ScreenManager):
            raise TypeError("shift_checklist.kv must define a ScreenManager root")
        return root

    def on_start(self) -> None:
        """Initialize local documents and optionally stop after smoke validation."""

        self.services.get("storage").initialize_all()
        if self.smoke_test:
            Clock.schedule_once(lambda _elapsed: self.stop(), 0.35)


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
            ShiftChecklistApp(
                smoke_test=True,
                data_directory=Path(temporary_directory),
            ).run()
    else:
        ShiftChecklistApp(
            smoke_test=args.smoke_test,
            data_directory=args.data_dir,
        ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
