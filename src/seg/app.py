"""Application factory for the Secure Execution Gateway (SEG).

This module exposes `create_app()` which constructs and configures the
FastAPI application used by the service. The ASGI application instance is
exported as `app` for use by ASGI servers (for example, uvicorn).
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core import (
    Settings,
    generic_exception_handler,
    http_exception_handler,
)
from .core import (
    settings as core_settings,
)
from .middleware.auth import AuthMiddleware
from .middleware.request_id import RequestIDMiddleware
from .routes.commands import router as commands_router
from .routes.health import router as health_router
from .routes.metrics import router as metrics_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    This function centralizes application construction so tests can instantiate
    a configured app with alternate settings. It performs the following
    responsibilities:

    - Instantiate application settings (Pydantic `Settings`).
    - Register middleware in the required order.
    - Register global exception handlers.
    - Include API routers.

    Args:
        settings: Optional pre-constructed Settings object for tests.

    Returns:
        A configured `FastAPI` application instance.
    """

    settings = settings or core_settings

    app = FastAPI(
        title="Secure Execution Gateway (SEG)",
        version="0.1.0",
    )

    # Attach settings to app state (single source of truth)
    app.state.settings = settings

    # Middlewares (order matters).
    # Note: Starlette executes the last-added middleware first, so we add Auth
    # then RequestID to ensure RequestID runs before Auth at request time.
    app.add_middleware(AuthMiddleware, api_token=settings.seg_api_token)
    app.add_middleware(RequestIDMiddleware)

    # Fallback exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(commands_router)

    return app


app = create_app()
