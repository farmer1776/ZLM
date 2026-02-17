import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from config import settings
from dependencies import _LoginRequired, get_flashed_messages
from middleware.audit_context import RequestContextMiddleware
from middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware
from template_filters import dateformat, filesizeformat_binary, status_badge, timesince

# Configure logging
os.makedirs(settings.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(settings.LOG_DIR, 'app.log')),
    ],
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url='/docs' if settings.DEBUG else None,
    redoc_url=None,
)

# Middleware (order matters - outermost first)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie='zlm_session',
    max_age=86400,  # 24 hours
)

# Static files
app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__), 'static')), name='static')

# Jinja2 Templates
_template_dir = os.path.join(os.path.dirname(__file__), 'templates')
templates = Jinja2Templates(directory=_template_dir)

# Register custom filters
templates.env.filters['status_badge'] = status_badge
templates.env.filters['filesizeformat_binary'] = filesizeformat_binary
templates.env.filters['timesince'] = timesince
templates.env.filters['dateformat'] = dateformat

# Add global template context
templates.env.globals['APP_NAME'] = settings.APP_NAME
templates.env.globals['APP_VERSION'] = settings.APP_VERSION


# Make templates and flash messages available in request.state
@app.middleware('http')
async def inject_template_context(request: Request, call_next):
    request.state.templates = templates
    response = await call_next(request)
    return response


# Handle login required exceptions
@app.exception_handler(_LoginRequired)
async def login_required_handler(request: Request, exc: _LoginRequired):
    return RedirectResponse(url=f'/auth/login/?next={exc.next_url}', status_code=302)


# Template context processor - inject user and messages into every template render
_original_template_response = templates.TemplateResponse


def _patched_template_response(name, context, **kwargs):
    request = context.get('request')
    if request:
        # Inject user info
        if 'user' not in context:
            from database import SessionLocal
            from models.user import User
            user_id = request.session.get('user_id')
            if user_id:
                db = SessionLocal()
                try:
                    context['user'] = db.query(User).filter(User.id == user_id).first()
                finally:
                    db.close()
            else:
                context['user'] = None

        # Inject flash messages
        context['messages'] = get_flashed_messages(request)
    return _original_template_response(name, context, **kwargs)


templates.TemplateResponse = _patched_template_response


# Include routers
from routers.auth import router as auth_router, _login_post_handler, _password_change_post_handler
from routers.dashboard import router as dashboard_router
from routers.accounts import router as accounts_router, _account_status_change_handler
from routers.audit import router as audit_router
from routers.bulk_ops import router as bulk_ops_router, _bulk_upload_post_handler
from routers.exports import router as exports_router

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(accounts_router)
app.include_router(audit_router)
app.include_router(bulk_ops_router)
app.include_router(exports_router)

# Add async form handlers as raw routes (POST handlers that need form data)
from starlette.routing import Route

app.routes.insert(0, Route('/auth/login/', _login_post_handler, methods=['POST']))
app.routes.insert(0, Route('/auth/password-change/', _password_change_post_handler, methods=['POST']))
app.routes.insert(0, Route('/accounts/{pk:int}/', _account_status_change_handler, methods=['POST']))
app.routes.insert(0, Route('/bulk/', _bulk_upload_post_handler, methods=['POST']))


# Ensure data directories exist
for d in [settings.UPLOAD_DIR, settings.EXPORT_DIR, settings.LOG_DIR]:
    os.makedirs(d, exist_ok=True)
