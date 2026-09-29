from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_HEADER = "x-request-id"
RESPONSE_TIME_HEADER = "x-response-time-ms"
# Chỉ nhận ID ngắn, an toàn từ client; header lạ (quá dài, có khoảng trắng/PII) thì sinh ID mới
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def new_correlation_id() -> str:
    return f"req-{uuid.uuid4().hex[:8]}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Xóa context của request trước để field không "rò" sang request sau
        clear_contextvars()

        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        correlation_id = incoming if _VALID_REQUEST_ID.match(incoming) else new_correlation_id()

        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers[REQUEST_ID_HEADER] = correlation_id
        response.headers[RESPONSE_TIME_HEADER] = f"{elapsed_ms:.2f}"
        return response
