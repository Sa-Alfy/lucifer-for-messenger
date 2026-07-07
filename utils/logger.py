"""
utils/logger.py — Centralised logging setup.

Rules:
  - stdout only (Render captures it; local disk is ephemeral and pointless).
  - No file handler, no rotation.
  - Log level is controlled by settings.log_level.
  - NEVER log secret values — tokens, keys, or connection strings.
    Log only which keys are present or absent, never their contents.
"""

import logging
import sys

from config import settings

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # httpx logs full request URLs at INFO, which can include API keys in query params.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, configuring the root logger once on first call."""
    _configure_root()
    return logging.getLogger(name)
