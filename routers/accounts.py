import math
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import settings
from dependencies import add_flash, get_db, require_login
from models.account import Account, AccountStatus
from models.audit import AuditLog
from models.user import User
from services.account_service import AccountService, VALID_TRANSITIONS

router = APIRouter(prefix='/accounts', tags=['accounts'])


@router.get('/')
def account_list(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    q = request.query_params.get('q', '').strip()
    status = request.query_params.get('status', '')
    domain = request.query_params.get('domain', '')
    page = int(request.query_params.get('page', '1'))

    query = db.query(Account).order_by(Account.email)

    if q:
        query = query.filter(or_(
            Account.email.ilike(f'%{q}%'),
            Account.display_name.ilike(f'%{q}%'),
        ))
    if status:
        query = query.filter(Account.status == status)
    if domain:
        query = query.filter(Account.domain == domain)

    total_count = query.count()
    per_page = settings.ACCOUNTS_PER_PAGE
    total_pages = max(1, math.ceil(total_count / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    accounts = query.offset(offset).limit(per_page).all()

    # Get distinct domains for filter dropdown
    domains = [row[0] for row in db.query(Account.domain).distinct().order_by(Account.domain).all()]

    # Build query string for pagination (without page param)
    qs_params = {}
    if q:
        qs_params['q'] = q
    if status:
        qs_params['status'] = status
    if domain:
        qs_params['domain'] = domain
    query_string = urlencode(qs_params)

    return request.state.templates.TemplateResponse('accounts/list.html', {
        'request': request,
        'user': user,
        'accounts': accounts,
        'total_count': total_count,
        'q': q,
        'current_status': status,
        'current_domain': domain,
        'status_choices': AccountStatus.choices,
        'domains': domains,
        'current_page': page,
        'total_pages': total_pages,
        'query_string': query_string,
    })


@router.get('/{pk}/')
def account_detail(request: Request, pk: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == pk).first()
    if not account:
        add_flash(request, 'Account not found.', 'danger')
        return RedirectResponse(url='/accounts/', status_code=302)

    # Valid transitions for status change form
    valid = VALID_TRANSITIONS.get(account.status, [])
    valid_transitions = [(s, AccountStatus.label(s)) for s in valid]

    purge_entries = account.purge_entries[:5]

    recent_logs = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == 'account', AuditLog.target_id == str(account.id))
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )

    return request.state.templates.TemplateResponse('accounts/detail.html', {
        'request': request,
        'user': user,
        'account': account,
        'valid_transitions': valid_transitions,
        'purge_entries': purge_entries,
        'recent_logs': recent_logs,
    })


# POST handler for status change needs async form parsing
from starlette.routing import Route


async def _account_status_change_handler(request: Request):
    from database import SessionLocal
    db = SessionLocal()
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return RedirectResponse(url='/auth/login/', status_code=302)

        pk = request.path_params['pk']
        user = db.query(User).filter(User.id == user_id).first()
        account = db.query(Account).filter(Account.id == pk).first()

        if not account:
            return RedirectResponse(url='/accounts/', status_code=302)

        form = await request.form()
        new_status = form.get('new_status', '')
        reason = form.get('reason', '')

        service = AccountService(db)
        success, message = service.change_status(
            account=account,
            new_status=new_status,
            user=user,
            reason=reason,
        )

        add_flash(request, message, 'success' if success else 'danger')
        return RedirectResponse(url=f'/accounts/{pk}/', status_code=302)
    finally:
        db.close()
