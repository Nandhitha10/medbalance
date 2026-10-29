"""FastAPI application factory with standard healthcheck, CORS, logging, and error handling."""

import logging
import time
from typing import Any, Callable
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from medbal_common.clock import now as sim_now
from medbal_common.logging import setup_logging

logger = logging.getLogger(__name__)


def create_app(
    name: str,
    title: str | None = None,
    lifespan: Any = None,
    **kwargs: Any,
) -> FastAPI:
    """Create a standardized FastAPI application instance for MedBalance services."""
    setup_logging(service_name=name)

    app = FastAPI(
        title=title or f"MedBalance - {name}",
        version="0.1.0",
        lifespan=lifespan,
        **kwargs,
    )

    # Standard CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next: Callable):
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} ({duration:.4f}s)",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_sec": round(duration, 4),
                },
            )
            return response
        except Exception as exc:
            duration = time.perf_counter() - start_time
            logger.error(
                f"Unhandled exception during {request.method} {request.url.path} ({duration:.4f}s): {exc}",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_sec": round(duration, 4),
                },
            )
            raise exc

    # Global unhandled exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "service": name,
                "detail": str(exc),
            },
        )

    # Base healthcheck endpoint (supports direct, prefixed, and gateway routing)
    short_name = name.replace("-api", "")
    @app.get("/health")
    @app.get(f"/api/{name}/health")
    @app.get(f"/api/{short_name}/health")
    async def healthcheck():
        return {
            "status": "ok",
            "service": name,
            "timestamp": sim_now().isoformat(),
        }


    return app
