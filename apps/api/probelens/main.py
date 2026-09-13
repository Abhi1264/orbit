from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from probelens.api.router import api_router
from probelens.config import get_settings
from probelens.core.logging import configure_logging, get_logger
from probelens.core.middleware import RequestContextMiddleware
from probelens.db.clickhouse import AnalyticsQueryError, get_readonly_client
from probelens.db.postgres import get_engine

log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info("startup", env=settings.app_env, llm_enabled=settings.llm_enabled, model=settings.llm_model)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Probelens API",
        version="0.1.0",
        description="Product analytics and experimentation platform for Threadline.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix="/api")

    @app.exception_handler(AnalyticsQueryError)
    async def analytics_error(_: Request, exc: AnalyticsQueryError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"detail": "Analytics query failed", "error": str(exc)[:300]}
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        status = {"api": "ok", "postgres": "ok", "clickhouse": "ok"}
        try:
            with get_engine().connect() as conn:
                conn.execute(text("select 1"))
        except Exception as exc:
            status["postgres"] = f"error: {str(exc)[:120]}"
        try:
            get_readonly_client().command("select 1")
        except Exception as exc:
            status["clickhouse"] = f"error: {str(exc)[:120]}"
        return status

    return app


app = create_app()
