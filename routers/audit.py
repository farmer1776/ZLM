import csv
import io
import math
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from config import settings
from dependencies import get_db, require_login
from models.audit import AuditAction, AuditLog
from models.user import User

router = APIRouter(prefix='/audit', tags=['audit'])


@router.get('/')
def audit_list(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    action = request.query_params.get('action', '')
    date_from = request.query_params.get('date_from', '')
    date_to = request.query_params.get('date_to', '')
    page = int(request.query_params.get('page', '1'))

    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())

    if action:
        query = query.filter(AuditLog.action == action)
    if date_from:
        try:
            dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= dt)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(AuditLog.created_at <= dt)
        except ValueError:
            pass

    total_count = query.count()
    per_page = settings.AUDIT_LOGS_PER_PAGE
    total_pages = max(1, math.ceil(total_count / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    logs = query.offset(offset).limit(per_page).all()

    # Build query string for pagination
    qs_params = {}
    if action:
        qs_params['action'] = action
    if date_from:
        qs_params['date_from'] = date_from
    if date_to:
        qs_params['date_to'] = date_to
    query_string = urlencode(qs_params)

    return request.state.templates.TemplateResponse('audit/list.html', {
        'request': request,
        'user': user,
        'logs': logs,
        'action_choices': AuditAction.choices,
        'current_action': action,
        'date_from': date_from,
        'date_to': date_to,
        'current_page': page,
        'total_pages': total_pages,
        'query_string': query_string,
    })


@router.get('/export/')
def audit_export(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    action = request.query_params.get('action', '')

    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.filter(AuditLog.action == action)

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['Timestamp', 'User', 'Action', 'Target Type', 'Target ID', 'IP Address', 'Details'])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for log in query.yield_per(500):
            writer.writerow([
                log.created_at.isoformat() if log.created_at else '',
                log.user.username if log.user else 'system',
                log.action_display,
                log.target_type,
                log.target_id,
                log.ip_address or '',
                str(log.details),
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        generate(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="audit_log.csv"'},
    )
