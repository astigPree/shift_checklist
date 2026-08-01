"""Application-owned rotating log configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIRECTORY_NAME = "logs"
LOG_FILENAME = "shift-checklist.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


def configure_logging(data_directory: Path) -> Path | None:
    """Attach one rotating file handler and return its path when available."""

    log_path = data_directory / LOG_DIRECTORY_NAME / LOG_FILENAME
    root_logger = logging.getLogger()
    for handler in tuple(root_logger.handlers):
        if getattr(handler, "shift_checklist_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as error:
        logging.getLogger(__name__).warning(
            "Application log is unavailable at %s: %s", log_path, error
        )
        return None

    handler.shift_checklist_handler = True  # type: ignore[attr-defined]
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(handler)
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    logging.getLogger(__name__).info("Application logging initialized")
    return log_path


def close_application_logging() -> None:
    """Flush and detach only Shift Checklist's application-owned handlers."""

    root_logger = logging.getLogger()
    for handler in tuple(root_logger.handlers):
        if getattr(handler, "shift_checklist_handler", False):
            root_logger.removeHandler(handler)
            handler.close()
