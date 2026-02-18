import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from config import settings
from dependencies import _LoginRequired, get_flashed_messages
from middleware.audit_context import RequestContextMiddleware
from middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware
from template_filters import dateformat, filesizeformat_binary, status_badge, timesince, timeuntil

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Determine whether to enable the scheduler.
    # Under Gunicorn the post_fork hook sets ZLM_SCHEDULER_ENABLED=1 only for
    # worker #1.  In dev (plain uvicorn) there is no hook, so we enable it
    # unconditionally unless the env var is explicitly set to something else.
    running_under_gunicorn = 'gunicorn' in os.environ.get('SERVER_SOFTWARE', '').lower()
    scheduler_enabled = (
        os.environ.get('ZLM_SCHEDULER_ENABLED') == '1'
        if running_under_gunicorn
        else True
    )

    if scheduler_enabled:
        from database import SessionLocal
        from services import scheduler as sched_service

        sched_service.scheduler.start()
        _logger = logging.getLogger(__name__)
        _logger.info('Scheduler: started')

        db = SessionLocal()
        try:
            interval = sched_service.get_sync_interval_hours(db)
        finally:
            db.close()

        sched_service.apply_schedule(interval)

    yield

    if scheduler_enabled:
        from services import scheduler as sched_service
        sched_service.scheduler.shutdown(wait=False)


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
    lifespan=lifespan,
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
templates.env.filters['timeuntil'] = timeuntil
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


# Health check
@app.get('/healthz')
async def healthz():
    from sqlalchemy import text
    from database import SessionLocal
    try:
        db = SessionLocal()
        db.execute(text('SELECT 1'))
        db.close()
        return JSONResponse({'status': 'ok'}, status_code=200)
    except Exception as e:
        return JSONResponse({'status': 'error', 'detail': str(e)}, status_code=503)


# Include routers
from routers.auth import router as auth_router, _login_post_handler, _password_change_post_handler
from routers.dashboard import router as dashboard_router
from routers.accounts import router as accounts_router, _account_status_change_handler
from routers.audit import router as audit_router
from routers.bulk_ops import router as bulk_ops_router, _bulk_upload_post_handler
from routers.exports import router as exports_router
from routers.settings import router as settings_router, _sync_now_post_handler, _schedule_change_post_handler

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(accounts_router)
app.include_router(audit_router)
app.include_router(bulk_ops_router)
app.include_router(exports_router)
app.include_router(settings_router)

# Add async form handlers as raw routes (POST handlers that need form data)
from starlette.routing import Route

app.routes.insert(0, Route('/auth/login/', _login_post_handler, methods=['POST']))
app.routes.insert(0, Route('/auth/password-change/', _password_change_post_handler, methods=['POST']))
app.routes.insert(0, Route('/accounts/{pk:int}/', _account_status_change_handler, methods=['POST']))
app.routes.insert(0, Route('/bulk/', _bulk_upload_post_handler, methods=['POST']))
app.routes.insert(0, Route('/settings/sync-now/', _sync_now_post_handler, methods=['POST']))
app.routes.insert(0, Route('/settings/schedule/', _schedule_change_post_handler, methods=['POST']))


# Ensure data directories exist
for d in [settings.UPLOAD_DIR, settings.EXPORT_DIR, settings.LOG_DIR]:
    os.makedirs(d, exist_ok=True)
