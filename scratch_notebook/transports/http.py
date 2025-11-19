"""HTTP and SSE transport implementation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth import AuthProvider
from fastmcp.server.http import (
    EventStore,
    SseServerTransport,
    StreamableHTTPASGIApp,
    StreamableHTTPSessionManager,
    build_resource_metadata_url,
    create_base_app,
)
from fastmcp.utilities.logging import temporary_log_level
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Mount, Route

from ..logging import get_logger

try:  # FastMCP >= 0.3
    from fastmcp.server.auth.middleware import RequireAuthMiddleware
except ModuleNotFoundError:  # pragma: no cover - fallback for older fastmcp
    RequireAuthMiddleware = None  # type: ignore

logger = get_logger(__name__)


@dataclass(slots=True)
class HttpTransportConfig:
    """Configuration for the HTTP/SSE transport layer."""

    host: str
    port: int
    http_path: str
    sse_path: str
    metrics_path: str
    enable_metrics: bool
    enable_http: bool
    enable_sse: bool
    socket_path: Path | None = None


def describe_routes(config: HttpTransportConfig) -> Mapping[str, str]:
    """Return a mapping of logical endpoints to their configured paths."""

    routes: dict[str, str] = {}
    if config.enable_http:
        routes["http"] = _normalise_path(config.http_path)
    if config.enable_sse:
        routes["sse"] = _normalise_path(config.sse_path)
    if config.enable_metrics:
        routes["metrics"] = _normalise_path(config.metrics_path)
    return routes


def run_http(server: FastMCP, config: HttpTransportConfig) -> None:
    """Run FastMCP HTTP and SSE transports using uvicorn."""

    if not (config.enable_http or config.enable_sse or config.enable_metrics):
        logger.info("transport.http.skip_all_disabled")
        return

    routes = describe_routes(config)
    context = {
        "host": config.host,
        "port": config.port,
        "routes": routes,
        "socket_path": str(config.socket_path) if config.socket_path else None,
    }

    async def _serve() -> None:
        app = _build_transport_app(server, config)
        log_level = logger.level if isinstance(logger.level, int) else None

        uvicorn_kwargs: dict[str, object] = {
            "timeout_graceful_shutdown": 0,
            "lifespan": "on",
            "ws": "websockets-sansio",
        }
        if config.socket_path is not None:
            uvicorn_kwargs["uds"] = str(config.socket_path)

        config_kwargs = {k: v for k, v in uvicorn_kwargs.items() if v is not None}

        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            **config_kwargs,
        )

        server_instance = uvicorn.Server(uvicorn_config)
        path_hint = getattr(app.state, "path", "/")

        logger.info(
            "transport.http.serve",
            extra={
                "context": {
                    **context,
                    "path": path_hint,
                }
            },
        )

        with temporary_log_level(level=log_level):
            await server_instance.serve()

    logger.info("transport.http.start", extra={"context": context})
    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        logger.info("transport.http.interrupted", extra={"context": context})
        raise
    except Exception:
        logger.exception("transport.http.failed", extra={"context": context})
        raise
    else:
        logger.info("transport.http.stop", extra={"context": context})


def _build_transport_app(
    server: FastMCP, config: HttpTransportConfig
):
    """Create a Starlette application exposing streamable HTTP and SSE."""

    routes: list[BaseRoute] = []
    middleware: list[Middleware] = []
    session_manager: StreamableHTTPSessionManager | None = None
    auth: AuthProvider | None = getattr(server, "auth", None)
    deprecated_settings = server._deprecated_settings  # type: ignore[attr-defined]

    http_path = _normalise_path(config.http_path)
    sse_path = _normalise_path(config.sse_path)
    message_path = _derive_message_path(config, deprecated_settings.message_path)

    if auth and RequireAuthMiddleware:
        middleware.extend(auth.get_middleware())

    if config.enable_http:
        session_manager = StreamableHTTPSessionManager(
            app=server._mcp_server,
            event_store=None,  # EventStore integration TBD
            json_response=deprecated_settings.json_response,
            stateless=deprecated_settings.stateless_http,
        )
        http_endpoint = StreamableHTTPASGIApp(session_manager)
        routes.extend(_build_http_routes(server, auth, http_path, http_endpoint))

    if config.enable_sse:
        routes.extend(
            _build_sse_routes(server, auth, sse_path, message_path)
        )

    routes.extend(server._get_additional_http_routes())

    @asynccontextmanager
    async def lifespan(_app):
        async with server._lifespan_manager():
            if session_manager is not None:
                async with session_manager.run():
                    yield
            else:
                yield

    app = create_base_app(
        routes=routes,
        middleware=middleware,
        debug=deprecated_settings.debug,
        lifespan=lifespan,
    )
    app.state.fastmcp_server = server
    app.state.path = http_path if config.enable_http else sse_path
    return app


def _build_http_routes(
    server: FastMCP,
    auth: AuthProvider | None,
    http_path: str,
    endpoint: StreamableHTTPASGIApp,
) -> list[BaseRoute]:
    routes: list[BaseRoute] = []

    if auth and RequireAuthMiddleware:
        routes.extend(auth.get_routes(mcp_path=http_path))
        resource_url = auth._get_resource_url(http_path)
        resource_metadata_url = (
            build_resource_metadata_url(resource_url) if resource_url else None
        )
        routes.append(
            Route(
                http_path,
                endpoint=RequireAuthMiddleware(
                    endpoint,
                    auth.required_scopes,
                    resource_metadata_url,
                ),
                methods=["GET", "POST", "DELETE"],
            )
        )
    else:
        routes.append(
            Route(
                http_path,
                endpoint=endpoint,
                methods=["GET", "POST", "DELETE"],
            )
        )
    return routes


def _build_sse_routes(
    server: FastMCP,
    auth: AuthProvider | None,
    sse_path: str,
    message_path: str,
) -> list[BaseRoute]:
    routes: list[BaseRoute] = []
    sse_transport = SseServerTransport(message_path)

    async def handle_sse(scope, receive, send):
        async with sse_transport.connect_sse(scope, receive, send) as streams:
            await server._mcp_server.run(
                streams[0],
                streams[1],
                server._mcp_server.create_initialization_options(),
            )
        return Response()

    if auth and RequireAuthMiddleware:
        routes.extend(auth.get_routes(mcp_path=sse_path))
        resource_url = auth._get_resource_url(sse_path)
        resource_metadata_url = (
            build_resource_metadata_url(resource_url) if resource_url else None
        )
        routes.append(
            Route(
                sse_path,
                endpoint=RequireAuthMiddleware(
                    handle_sse,
                    auth.required_scopes,
                    resource_metadata_url,
                ),
                methods=["GET"],
            )
        )
        routes.append(
            Mount(
                message_path,
                app=RequireAuthMiddleware(
                    sse_transport.handle_post_message,
                    auth.required_scopes,
                    resource_metadata_url,
                ),
            )
        )
    else:
        async def sse_endpoint(request):
            return await handle_sse(request.scope, request.receive, request._send)  # type: ignore[attr-defined]

        routes.append(
            Route(
                sse_path,
                endpoint=sse_endpoint,
                methods=["GET"],
            )
        )
        routes.append(Mount(message_path, app=sse_transport.handle_post_message))
    return routes


def _normalise_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _derive_message_path(config: HttpTransportConfig, default_message_path: str) -> str:
    if not config.enable_sse:
        return default_message_path
    base = _normalise_path(config.sse_path)
    if base == "/":
        candidate = "/messages"
    else:
        candidate = f"{base}/messages"
    return candidate
