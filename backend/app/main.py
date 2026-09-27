from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.services.errors import InvalidStep, NotFound, ServiceError, SessionFinished

STATUS_FOR_ERROR: dict[type[ServiceError], int] = {
    NotFound: 404,
    InvalidStep: 400,
    SessionFinished: 409,
}


def create_app() -> FastAPI:
    app = FastAPI(title="Mziko API", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.include_router(router, prefix="/api")

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=STATUS_FOR_ERROR.get(type(exc), 400))

    return app


app = create_app()
