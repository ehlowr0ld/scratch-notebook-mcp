"""Logging utilities for the Scratch Notebook MCP server."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastmcp.utilities.logging import configure_logging as _fastmcp_configure_logging

_PACKAGE_LOGGER_NAME = "scratch_notebook"
_CONFIGURED = False


def _qualify(name: str | None) -> str:
    if not name:
        return _PACKAGE_LOGGER_NAME
    if name.startswith(_PACKAGE_LOGGER_NAME):
        return name
    return f"{_PACKAGE_LOGGER_NAME}.{name}"


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | int = "INFO",
    **rich_kwargs: Any,
) -> logging.Logger:
    """Configure FastMCP logging so all output is routed correctly.

    Logs are written to stderr in stdio mode and forwarded via telemetry
    notifications for HTTP transports, matching MCP expectations.
    """

    global _CONFIGURED

    logger = logging.getLogger(_PACKAGE_LOGGER_NAME)
    _fastmcp_configure_logging(level=level, logger=logger, **rich_kwargs)

    _CONFIGURED = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger scoped to the package namespace."""

    if not _CONFIGURED:
        configure_logging()

    qualified = _qualify(name)
    return logging.getLogger(qualified)
