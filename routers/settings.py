import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from dependencies import add_flash, get_db, require_login
from models.setting import SYNC_INTERVAL_CHOICES, SettingKey, get_setting, set_setting
from models.sync import SyncHistory
from models.user import User
from services import scheduler as sched_service

router = APIRouter(prefix='/settings', tags=['settings'])


@router.get('/')
def settings_page(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    recent_syncs = (
        db.query(SyncHistory)
        .order_by(SyncHistory.started_at.desc())
        .limit(5)
        .all()
    )
    last_sync = recent_syncs[0] if recent_syncs else None

    current_interval = get_setting(db, SettingKey.SYNC_INTERVAL_HOURS, default='0')
    next_run = sched_service.get_next_run_time()

    return request.state.templates.TemplateResponse('settings/index.html', {
        'request': request,
        'last_sync': last_sync,
        'recent_syncs': recent_syncs,
        'current_interval': current_interval,
        'next_run': next_run,
        'sync_interval_choices': SYNC_INTERVAL_CHOICES,
    })


@router.get('/api/last-sync/')
def api_last_sync(request: Request, user=Depends(require_login), db: Session = Depends(get_db)):
    """JSON endpoint: returns the most recent sync record for live dashboard polling."""
    sync = db.query(SyncHistory).order_by(SyncHistory.started_at.desc()).first()
    if not sync:
        return JSONResponse({'status': None})

    now = datetime.utcnow()
    diff = now - sync.started_at.replace(tzinfo=None)
    seconds = int(diff.total_seconds())
    if seconds < 60:
        started_ago = f'{seconds} seconds ago'
    elif seconds < 3600:
        m = seconds // 60
        started_ago = f'{m} minute{"s" if m != 1 else ""} ago'
    else:
        h = seconds // 3600
        started_ago = f'{h} hour{"s" if h != 1 else ""} ago'

    duration_seconds = None
    if sync.duration:
        duration_seconds = int(sync.duration.total_seconds())

    return JSONResponse({
        'status': sync.status,
        'started_ago': started_ago,
        'total_accounts': sync.total_accounts,
        'created_count': sync.created_count,
        'updated_count': sync.updated_count,
        'unchanged_count': sync.unchanged_count,
        'error_count': sync.error_count,
        'duration_seconds': duration_seconds,
    })


async def _sync_now_post_handler(request: Request):
    """Spawn a daemon thread to run sync and redirect back to settings."""
    from database import SessionLocal
    from services import sync_service

    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url='/auth/login/', status_code=302)

    def _run():
        db = SessionLocal()
        try:
            sync_service.sync_accounts(db)
        except Exception:
            pass
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    add_flash(request, 'Sync started in the background.', 'info')
    return RedirectResponse(url='/settings/', status_code=302)


async def _schedule_change_post_handler(request: Request):
    """Persist new schedule interval and apply it to the scheduler."""
    from database import SessionLocal

    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url='/auth/login/', status_code=302)

    form = await request.form()
    interval_str = form.get('interval', '0').strip()

    valid_values = {v for v, _ in SYNC_INTERVAL_CHOICES}
    if interval_str not in valid_values:
        add_flash(request, 'Invalid schedule value.', 'danger')
        return RedirectResponse(url='/settings/', status_code=302)

    db = SessionLocal()
    try:
        set_setting(db, SettingKey.SYNC_INTERVAL_HOURS, interval_str)
        interval_hours = int(interval_str)
        sched_service.apply_schedule(interval_hours)

        if interval_hours == 0:
            add_flash(request, 'Auto-sync disabled.', 'success')
        else:
            label = next(lbl for val, lbl in SYNC_INTERVAL_CHOICES if val == interval_str)
            add_flash(request, f'Auto-sync schedule set to: {label}.', 'success')
    finally:
        db.close()

    return RedirectResponse(url='/settings/', status_code=302)
