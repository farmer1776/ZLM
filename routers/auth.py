from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from dependencies import get_db, require_login, add_flash
from middleware.audit_context import get_current_ip
from models.audit import AuditAction, AuditLog
from models.user import User

router = APIRouter(prefix='/auth', tags=['auth'])


@router.get('/login/')
def login_page(request: Request):
    user_id = request.session.get('user_id')
    if user_id:
        return RedirectResponse(url='/', status_code=302)
    return request.state.templates.TemplateResponse('auth/login.html', {
        'request': request,
        'error': None,
    })


@router.post('/login/')
def login_submit(request: Request, db: Session = Depends(get_db)):
    import asyncio
    # We need to read form data - use sync approach
    # FastAPI runs sync def in threadpool, but we need form data
    # Use starlette's sync form parsing
    pass


# Use a raw starlette approach for form handling
from starlette.routing import Route


async def _login_post_handler(request: Request):
    from database import SessionLocal
    db = SessionLocal()
    try:
        form = await request.form()
        username = form.get('username', '').strip()
        password = form.get('password', '')
        ip = get_current_ip()

        user = db.query(User).filter(User.username == username).first()

        if user and user.is_active and user.check_password(password):
            request.session['user_id'] = user.id
            request.session['username'] = user.username
            user.last_login = datetime.utcnow()
            db.commit()

            audit = AuditLog(user_id=user.id, action=AuditAction.LOGIN, ip_address=ip)
            db.add(audit)
            db.commit()

            next_url = request.query_params.get('next', '/')
            return RedirectResponse(url=next_url, status_code=302)
        else:
            audit = AuditLog(
                action=AuditAction.LOGIN_FAILED,
                ip_address=ip,
            )
            audit.details = {'username': username}
            db.add(audit)
            db.commit()

            templates = request.state.templates
            return templates.TemplateResponse('auth/login.html', {
                'request': request,
                'error': 'Invalid username or password.',
            })
    finally:
        db.close()


@router.get('/logout/')
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('user_id')
    if user_id:
        ip = get_current_ip()
        audit = AuditLog(user_id=user_id, action=AuditAction.LOGOUT, ip_address=ip)
        db.add(audit)
        db.commit()
    request.session.clear()
    return RedirectResponse(url='/auth/login/', status_code=302)


@router.get('/password-change/')
def password_change_page(request: Request, user: User = Depends(require_login)):
    return request.state.templates.TemplateResponse('auth/password_change.html', {
        'request': request,
        'user': user,
        'errors': [],
    })


async def _password_change_post_handler(request: Request):
    from database import SessionLocal
    db = SessionLocal()
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return RedirectResponse(url='/auth/login/', status_code=302)

        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            return RedirectResponse(url='/auth/login/', status_code=302)

        form = await request.form()
        old_password = form.get('old_password', '')
        new_password1 = form.get('new_password1', '')
        new_password2 = form.get('new_password2', '')

        errors = []
        if not user.check_password(old_password):
            errors.append('Current password is incorrect.')
        if new_password1 != new_password2:
            errors.append('New passwords do not match.')
        if len(new_password1) < 8:
            errors.append('New password must be at least 8 characters.')

        if errors:
            templates = request.state.templates
            return templates.TemplateResponse('auth/password_change.html', {
                'request': request,
                'user': user,
                'errors': errors,
            })

        user.set_password(new_password1)
        db.commit()

        ip = get_current_ip()
        audit = AuditLog(user_id=user.id, action=AuditAction.PASSWORD_CHANGE, ip_address=ip)
        db.add(audit)
        db.commit()

        add_flash(request, 'Password changed successfully.', 'success')
        return RedirectResponse(url='/', status_code=302)
    finally:
        db.close()
