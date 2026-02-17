import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from .base import Base


class AuditAction:
    STATUS_CHANGE = 'status_change'
    BULK_OP = 'bulk_op'
    SYNC = 'sync'
    PURGE = 'purge'
    EXPORT = 'export'
    LOGIN = 'login'
    LOGOUT = 'logout'
    LOGIN_FAILED = 'login_failed'
    PASSWORD_CHANGE = 'password_change'

    choices = [
        ('status_change', 'Status Change'),
        ('bulk_op', 'Bulk Operation'),
        ('sync', 'Sync'),
        ('purge', 'Purge'),
        ('export', 'Export'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('login_failed', 'Login Failed'),
        ('password_change', 'Password Change'),
    ]

    @classmethod
    def label(cls, value):
        return dict(cls.choices).get(value, value)


class AuditLog(Base):
    __tablename__ = 'audit_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user = relationship('User', foreign_keys=[user_id])
    action = Column(String(30), nullable=False, index=True)
    target_type = Column(String(50), default='')
    target_id = Column(String(100), default='')
    ip_address = Column(String(45), nullable=True)
    _details = Column('details', Text, default='{}')
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index('idx_audit_time_action', created_at.desc(), 'action'),
    )

    @property
    def details(self):
        try:
            return json.loads(self._details) if self._details else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @details.setter
    def details(self, value):
        self._details = json.dumps(value) if value else '{}'

    @property
    def action_display(self):
        return AuditAction.label(self.action)

    def __repr__(self):
        return f"<AuditLog {self.created_at} - {self.action}>"
