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
_DEFAULT_SECRET = "change-me-in-production-32-chars-min"

@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    settings = get_settings()
    if settings.is_production and settings.secret_key == _DEFAULT_SECRET:
        raise RuntimeError("SECRET_KEY must be set in production")
    log.info("startup", env=settings.app_env, llm_enabled=settings.llm_enabled, model=settings.llm_model)
    yield

def create_app() -> FastAPI:
    settings = get_settings()
    docs = None if settings.is_production else "/api/docs"
    spec = None if settings.is_production else "/api/openapi.json"
    app = FastAPI(
        title="Orbit API",
        version="0.1.0",
        description="Product analytics and experimentation for Threadline.",
        lifespan=lifespan,
        docs_url=docs,
        openapi_url=spec,
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix="/api")

    @app.exception_handler(AnalyticsQueryError)
    async def analytics_error(_: Request, exc: AnalyticsQueryError) -> JSONResponse:
        log.warning("analytics_query_failed", error=str(exc)[:300])
        return JSONResponse(status_code=502, content={"detail": "Analytics query failed"})

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.exception("unhandled_error", path=request.url.path, request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        status = {"api": "ok", "postgres": "ok", "clickhouse": "ok"}
        try:
            with get_engine().connect() as conn:
                conn.execute(text("select 1"))
        except Exception:
            log.exception("health_postgres")
            status["postgres"] = "error"
        try:
            get_readonly_client().command("select 1")
        except Exception:
            log.exception("health_clickhouse")
            status["clickhouse"] = "error"
        return status

    return app

app = create_app()
