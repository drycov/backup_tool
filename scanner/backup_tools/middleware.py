"""HTTP middleware: correlation id из заголовка или новый."""

from __future__ import annotations

import logging

from services.correlation import get_correlation_id, new_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)

HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cid = (request.headers.get(HEADER) or "").strip() or new_correlation_id()
        set_correlation_id(cid)
        request.correlation_id = cid
        response = self.get_response(request)
        response[HEADER] = get_correlation_id() or cid
        return response
