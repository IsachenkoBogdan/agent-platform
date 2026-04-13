from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.registry.app.auth import build_registry_access_policy
from services.registry.app.routes.agents import router as agents_router
from services.registry.app.routes.health import router as health_router
from services.registry.app.routes.metrics import router as metrics_router
from services.registry.app.routes.providers import router as providers_router
from services.registry.app.service import RegistryService
from services.registry.app.store import InMemoryRegistryStore
from shared.config import get_settings
from shared.contracts import ErrorResponse
from shared.errors import AppError


def create_app() -> FastAPI:
    get_settings.cache_clear()
    settings = get_settings()
    app = FastAPI(title="registry", version="0.1.0")
    app.state.registry_service = RegistryService(store=InMemoryRegistryStore())
    app.state.registry_access_policy = build_registry_access_policy(settings)

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        payload = ErrorResponse(**exc.to_response()).model_dump(exclude_none=True)
        return JSONResponse(status_code=exc.status_code, content=payload)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(providers_router)
    app.include_router(agents_router)
    return app


app = create_app()
