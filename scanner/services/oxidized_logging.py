from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

_CONFIGURED = False
_OX_ENGINE_LOGGER = "services.oxidized_engine"


def oxidized_engine() -> str:
    return getattr(settings, "OXIDIZED_ENGINE", "python").lower()


def is_python_engine() -> bool:
    return oxidized_engine() == "python"


def is_ruby_engine() -> bool:
    return not is_python_engine()


def engine_title() -> str:
    if is_python_engine():
        return "Python Oxidized"
    return "Ruby Oxidized"


def default_log_path() -> Path:
    if is_python_engine():
        return Path(
            getattr(
                settings,
                "OXIDIZED_PYTHON_LOG_PATH",
                "/var/lib/oxidized/oxidized-python.log",
            )
        )
    return Path(getattr(settings, "OXIDIZED_LOG_PATH", "/var/lib/oxidized/oxidized.log"))


def log_path_from_config() -> Path | None:
    from services.oxidized_config_loader import load_oxidized_yaml

    log_value = load_oxidized_yaml().get("log")
    if not log_value:
        return None
    return Path(str(log_value))


def oxidized_log_path() -> Path:
    """Active log file for the current engine (UI tail + file handler)."""
    if is_ruby_engine():
        return log_path_from_config() or default_log_path()
    return default_log_path()


def configure_oxidized_file_logging() -> Path | None:
    """Oxidized-style file logging for the Python engine only."""
    global _CONFIGURED
    if not is_python_engine():
        return None
    if _CONFIGURED:
        return oxidized_log_path()

    log_path = oxidized_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s -- : %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        engine_logger = logging.getLogger(_OX_ENGINE_LOGGER)
        engine_logger.setLevel(logging.INFO)
        engine_logger.propagate = False
        for existing in list(engine_logger.handlers):
            if isinstance(existing, logging.FileHandler):
                engine_logger.removeHandler(existing)
        engine_logger.addHandler(handler)
        engine_logger.info(
            "oxidized | engine | %s | log=%s",
            engine_title(),
            log_path,
        )
        _CONFIGURED = True
        return log_path
    except OSError as exc:
        logging.getLogger(_OX_ENGINE_LOGGER).warning(
            "oxidized | log file unavailable: %s", exc
        )
        return None


def get_engine_logger(name: str | None = None) -> logging.Logger:
    """Logger that writes to oxidized log when Python engine is active."""
    if name:
        return logging.getLogger(f"{_OX_ENGINE_LOGGER}.{name}")
    return logging.getLogger(_OX_ENGINE_LOGGER)
