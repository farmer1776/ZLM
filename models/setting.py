from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Session, mapped_column

from .base import Base


class SettingKey:
    SYNC_INTERVAL_HOURS = 'sync_interval_hours'


SYNC_INTERVAL_CHOICES = [
    ('0', 'Off'),
    ('1', 'Every 1 hour'),
    ('2', 'Every 2 hours'),
    ('4', 'Every 4 hours'),
    ('8', 'Every 8 hours'),
    ('12', 'Every 12 hours'),
    ('24', 'Every 24 hours'),
]


class Setting(Base):
    __tablename__ = 'settings'

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    key = mapped_column(String(100), nullable=False, unique=True)
    value = mapped_column(String(500), nullable=False, default='')
    updated_at = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_settings_key', 'key', unique=True),
    )


def get_setting(db: Session, key: str, default: str = '') -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        row = Setting(key=key, value=value)
        db.add(row)
    db.commit()
