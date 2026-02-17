import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from dependencies import get_db, require_login
from models.account import Account
from models.audit import AuditAction, AuditLog
from models.user import User

router = APIRouter(prefix='/exports', tags=['exports'])


@router.get('/accounts/')
def export_accounts(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    status = request.query_params.get('status', '')
    domain = request.query_params.get('domain', '')

    query = db.query(Account).order_by(Account.email)
    if status:
        query = query.filter(Account.status == status)
    if domain:
        query = query.filter(Account.domain == domain)

    # Audit log
    audit = AuditLog(
        user_id=user.id,
        action=AuditAction.EXPORT,
        target_type='accounts',
    )
    audit.details = {
        'filters': {'status': status, 'domain': domain},
    }
    db.add(audit)
    db.commit()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            'Email', 'Display Name', 'Domain', 'Status', 'Zimbra Status',
            'Forwarding Address', 'Mailbox Size', 'Last Login',
            'Closed At', 'Purge Eligible Date', 'COS',
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for account in query.yield_per(500):
            writer.writerow([
                account.email,
                account.display_name,
                account.domain,
                account.status,
                account.zimbra_status,
                account.forwarding_address,
                account.mailbox_size,
                account.last_login_at.isoformat() if account.last_login_at else '',
                account.closed_at.isoformat() if account.closed_at else '',
                account.purge_eligible_date.isoformat() if account.purge_eligible_date else '',
                account.cos_name,
            ])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        generate(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="accounts_export.csv"'},
    )
