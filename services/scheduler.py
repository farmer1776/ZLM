import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from models.setting import SettingKey, get_setting

logger = logging.getLogger(__name__)

_JOB_ID = 'auto_sync'

scheduler = BackgroundScheduler(
    job_defaults={
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 60,
    }
)


def _run_sync_job():
    """Background job: open its own DB session and run sync_accounts."""
    from database import SessionLocal
    from services import sync_service

    db: Session = SessionLocal()
    try:
        logger.info('Scheduler: starting auto-sync')
        result = sync_service.sync_accounts(db)
        logger.info(
            'Scheduler: auto-sync complete — total=%d created=%d updated=%d errors=%d',
            result['total'], result['created'], result['updated'], result['errors'],
        )
    except Exception as exc:
        logger.error('Scheduler: auto-sync failed: %s', exc)
    finally:
        db.close()


def apply_schedule(interval_hours: int) -> None:
    """Remove existing job then re-add with the given interval (0 = disable)."""
    if scheduler.get_job(_JOB_ID):
        scheduler.remove_job(_JOB_ID)

    if interval_hours > 0:
        scheduler.add_job(
            _run_sync_job,
            trigger=IntervalTrigger(hours=interval_hours),
            id=_JOB_ID,
            replace_existing=True,
        )
        logger.info('Scheduler: auto-sync set to every %d hour(s)', interval_hours)
    else:
        logger.info('Scheduler: auto-sync disabled')


def get_next_run_time():
    """Return the next scheduled run datetime, or None."""
    job = scheduler.get_job(_JOB_ID)
    return job.next_run_time if job else None


def get_sync_interval_hours(db: Session) -> int:
    """Read the persisted interval from the settings table."""
    raw = get_setting(db, SettingKey.SYNC_INTERVAL_HOURS, default='0')
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0
