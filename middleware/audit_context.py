from __future__ import annotations

import contextvars
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_ip_address: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('ip_address', default=None)
_current_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar('current_user_id', default=None)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Store request context (IP, user) for use in audit logging."""

    async def dispatch(self, request: Request, call_next):
        ip = _get_client_ip(request)
        _ip_address.set(ip)

        user_id = request.session.get('user_id') if hasattr(request, 'session') else None
        _current_user_id.set(user_id)

        response = await call_next(request)
        return response


def get_current_ip() -> Optional[str]:
    return _ip_address.get()


def get_current_user_id() -> Optional[int]:
    return _current_user_id.get()


def _get_client_ip(request: Request) -> str:
    x_forwarded = request.headers.get('x-forwarded-for')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.client.host if request.client else '127.0.0.1'
