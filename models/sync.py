import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text

from .base import Base


class SyncStatus:
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class SyncHistory(Base):
    __tablename__ = 'sync_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default=SyncStatus.RUNNING)
    total_accounts = Column(Integer, default=0)
    created_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    unchanged_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    _error_details = Column('error_details', Text, default='[]')

    @property
    def error_details(self):
        try:
            return json.loads(self._error_details) if self._error_details else []
        except (json.JSONDecodeError, TypeError):
            return []

    @error_details.setter
    def error_details(self, value):
        self._error_details = json.dumps(value) if value else '[]'

    @property
    def duration(self):
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return None

    def __repr__(self):
        return f"<SyncHistory {self.started_at} - {self.status}>"
