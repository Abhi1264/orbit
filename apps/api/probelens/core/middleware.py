import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from probelens.core.logging import get_logger

log = get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed", method=request.method, path=request.url.path)
            raise
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers[REQUEST_ID_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if not request.url.path.endswith("/health"):
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=elapsed_ms,
            )
        return response
