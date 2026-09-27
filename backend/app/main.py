from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.parent_routes import router as parent_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services import parents
from app.services.errors import InvalidStep, NotFound, ServiceError, SessionFinished

STATUS_FOR_ERROR: dict[type[ServiceError], int] = {
    NotFound: 404,
    InvalidStep: 400,
    SessionFinished: 409,
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """The API owns the database, so the first parents from ADMIN_TELEGRAM_IDS are made here."""
    async with get_sessionmaker()() as db:
        await parents.ensure_admin_parents(db, get_settings().admin_telegram_ids)
        await db.commit()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mziko API", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan
    )
    app.include_router(router, prefix="/api")
    app.include_router(parent_router, prefix="/api/parent")

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=STATUS_FOR_ERROR.get(type(exc), 400))

    return app


app = create_app()
