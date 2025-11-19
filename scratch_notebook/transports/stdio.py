"""Minimal stdio transport wiring."""

from __future__ import annotations

from fastmcp import FastMCP

from ..logging import get_logger

logger = get_logger(__name__)


def run_stdio(server: FastMCP, *, show_banner: bool = True) -> None:
    """Run the server using the MCP stdio transport."""

    context = {"show_banner": bool(show_banner)}
    logger.info("transport.stdio.start", extra={"context": context})
    try:
        server.run(transport="stdio", show_banner=show_banner)
    except KeyboardInterrupt:
        logger.info("transport.stdio.interrupted", extra={"context": context})
        raise
    except Exception:  # pragma: no cover - defensive
        logger.exception("transport.stdio.failed", extra={"context": context})
        raise
    else:
        logger.info("transport.stdio.stop", extra={"context": context})
