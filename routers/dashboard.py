import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from dependencies import get_db, require_login
from models.account import Account, AccountStatus, PurgeQueue, PurgeQueueStatus
from models.audit import AuditLog
from models.sync import SyncHistory
from models.user import User

router = APIRouter(tags=['dashboard'])

# Simple in-memory cache for dashboard stats
_stats_cache = {'data': None, 'expires': 0}


@router.get('/')
def dashboard(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    now = time.time()
    if _stats_cache['data'] and _stats_cache['expires'] > now:
        stats = _stats_cache['data']
    else:
        stats = _build_stats(db)
        _stats_cache['data'] = stats
        _stats_cache['expires'] = now + 300  # 5 minute TTL

    # Always fetch the last sync fresh — bypasses the 5-min cache so the
    # dashboard reflects a just-completed background sync immediately.
    last_sync = db.query(SyncHistory).order_by(SyncHistory.started_at.desc()).first()
    stats['last_sync'] = last_sync

    return request.state.templates.TemplateResponse('dashboard/index.html', {
        'request': request,
        'user': user,
        'stats': stats,
    })


def _build_stats(db: Session):
    # Status counts
    status_rows = (
        db.query(Account.status, func.count(Account.id))
        .group_by(Account.status)
        .all()
    )
    status_counts = dict(status_rows)
    total = sum(status_counts.values())

    # Domain breakdown
    domain_rows = (
        db.query(Account.domain, func.count(Account.id).label('count'))
        .group_by(Account.domain)
        .order_by(func.count(Account.id).desc())
        .limit(10)
        .all()
    )
    domain_counts = [{'domain': row[0], 'count': row[1]} for row in domain_rows]

    # Pending purge
    today = datetime.utcnow().date()
    pending_purge = db.query(func.count(PurgeQueue.id)).filter(
        PurgeQueue.status == PurgeQueueStatus.WAITING,
        PurgeQueue.eligible_date <= today,
    ).scalar() or 0

    upcoming_purge = db.query(func.count(PurgeQueue.id)).filter(
        PurgeQueue.status == PurgeQueueStatus.WAITING,
    ).scalar() or 0

    # Recent activity
    recent_logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(10).all()

    # Last sync
    last_sync = db.query(SyncHistory).order_by(SyncHistory.started_at.desc()).first()

    # Protected accounts count
    protected_count = db.query(func.count(Account.id)).filter(
        Account.forwarding_address != '',
        Account.forwarding_address.isnot(None),
    ).scalar() or 0

    return {
        'total_accounts': total,
        'active_count': status_counts.get(AccountStatus.ACTIVE, 0),
        'locked_count': status_counts.get(AccountStatus.LOCKED, 0),
        'closed_count': status_counts.get(AccountStatus.CLOSED, 0),
        'pending_purge_count': status_counts.get(AccountStatus.PENDING_PURGE, 0),
        'purged_count': status_counts.get(AccountStatus.PURGED, 0),
        'domain_counts': domain_counts,
        'pending_purge_queue': pending_purge,
        'upcoming_purge': upcoming_purge,
        'protected_count': protected_count,
        'recent_logs': recent_logs,
        'last_sync': last_sync,
    }
