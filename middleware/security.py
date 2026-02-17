import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if not settings.DEBUG:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "font-src 'self';"
            )
        return response


# In-memory rate limit store (simple dict-based, suitable for single-process)
_rate_limit_store = {}  # type: dict


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit login attempts per IP."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == settings.LOGIN_URL and request.method == 'POST':
            ip = _get_client_ip(request)
            cache_key = f'login_attempts:{ip}'
            now = time.time()
            window = settings.RATE_LIMIT_LOGIN_WINDOW
            max_attempts = settings.RATE_LIMIT_LOGIN_ATTEMPTS

            attempts = _rate_limit_store.get(cache_key, [])
            attempts = [t for t in attempts if now - t < window]

            if len(attempts) >= max_attempts:
                return JSONResponse(
                    {'error': 'Too many login attempts. Please try again later.'},
                    status_code=429,
                )

            attempts.append(now)
            _rate_limit_store[cache_key] = attempts

        return await call_next(request)


def _get_client_ip(request: Request) -> str:
    x_forwarded = request.headers.get('x-forwarded-for')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.client.host if request.client else '127.0.0.1'
