from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import models  # noqa: F401  (تسجيل النماذج في Base.metadata)
from app.api import (
    routes_auth,
    routes_broadcast,
    routes_catalog,
    routes_notifications,
    routes_rag,
    routes_requests,
    routes_schedule,
)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.services.errors import (
    AccessDeniedError,
    BusinessRuleError,
    IngestionError,
    LLMNotConfiguredError,
    LLMOutputError,
    NotFoundError,
    NotGroundedError,
    PlatformError,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if settings.is_sqlite or settings.app_env == "development":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_catalog.router)
app.include_router(routes_rag.router)
app.include_router(routes_requests.router)
app.include_router(routes_schedule.router)
app.include_router(routes_broadcast.router)
app.include_router(routes_notifications.router)

_ERROR_STATUS: list[tuple[type[PlatformError], int]] = [
    (AccessDeniedError, 403),
    (NotFoundError, 404),
    (BusinessRuleError, 400),
    (NotGroundedError, 400),
    (IngestionError, 400),
    (LLMNotConfiguredError, 503),
    (LLMOutputError, 502),
    (PlatformError, 500),
]


@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    status_code = 500
    for error_type, code in _ERROR_STATUS:
        if isinstance(exc, error_type):
            status_code = code
            break
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})




@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}