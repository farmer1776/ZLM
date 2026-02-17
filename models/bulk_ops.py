import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from .base import Base


class BulkOperationStatus:
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

    choices = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    @classmethod
    def label(cls, value):
        return dict(cls.choices).get(value, value)


class BulkOperationType:
    LOCK = 'lock'
    CLOSE = 'close'
    REACTIVATE = 'reactivate'

    choices = [
        ('lock', 'Lock Accounts'),
        ('close', 'Close Accounts'),
        ('reactivate', 'Reactivate Accounts'),
    ]

    @classmethod
    def label(cls, value):
        return dict(cls.choices).get(value, value)


class BulkOperation(Base):
    __tablename__ = 'bulk_operations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    user = relationship('User', foreign_keys=[user_id])
    operation_type = Column(String(20), nullable=False)
    filename = Column(String(255), default='')
    total_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    status = Column(String(20), default=BulkOperationStatus.PENDING)
    _results = Column('results', Text, default='[]')
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    @property
    def results(self):
        try:
            return json.loads(self._results) if self._results else []
        except (json.JSONDecodeError, TypeError):
            return []

    @results.setter
    def results(self, value):
        self._results = json.dumps(value) if value else '[]'

    @property
    def success_count(self):
        return self.processed_count - self.error_count

    @property
    def operation_type_display(self):
        return BulkOperationType.label(self.operation_type)

    @property
    def status_display(self):
        return BulkOperationStatus.label(self.status)

    def __repr__(self):
        return f"<BulkOperation {self.operation_type} - {self.status}>"
