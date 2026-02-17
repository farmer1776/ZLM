from datetime import datetime

from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, Date,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from .base import Base


class AccountStatus:
    ACTIVE = 'active'
    LOCKED = 'locked'
    CLOSED = 'closed'
    PENDING_PURGE = 'pending_purge'
    PURGED = 'purged'

    choices = [
        ('active', 'Active'),
        ('locked', 'Locked'),
        ('closed', 'Closed'),
        ('pending_purge', 'Pending Purge'),
        ('purged', 'Purged'),
    ]

    @classmethod
    def label(cls, value):
        return dict(cls.choices).get(value, value)


class ZimbraStatus:
    ACTIVE = 'active'
    LOCKED = 'locked'
    CLOSED = 'closed'


class PurgeQueueStatus:
    WAITING = 'waiting'
    APPROVED = 'approved'
    EXECUTED = 'executed'
    CANCELLED = 'cancelled'
    SKIPPED = 'skipped'

    choices = [
        ('waiting', 'Waiting'),
        ('approved', 'Approved'),
        ('executed', 'Executed'),
        ('cancelled', 'Cancelled'),
        ('skipped', 'Skipped'),
    ]

    @classmethod
    def label(cls, value):
        return dict(cls.choices).get(value, value)


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    zimbra_id = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), default='')
    domain = Column(String(255), index=True, default='')

    status = Column(String(20), default=AccountStatus.ACTIVE, index=True)
    zimbra_status = Column(String(20), default=ZimbraStatus.ACTIVE)

    forwarding_address = Column(String(255), default='')
    mailbox_size = Column(BigInteger, default=0)
    last_login_at = Column(DateTime, nullable=True)
    cos_name = Column(String(128), default='')

    closed_at = Column(DateTime, nullable=True)
    purge_eligible_date = Column(Date, nullable=True, index=True)
    purged_at = Column(DateTime, nullable=True)

    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    status_changed_by = relationship('User', foreign_keys=[status_changed_by_id])

    sync_hash = Column(String(32), default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    purge_entries = relationship('PurgeQueue', back_populates='account', order_by='PurgeQueue.eligible_date')

    __table_args__ = (
        Index('idx_domain_status', 'domain', 'status'),
    )

    @property
    def is_protected(self):
        return bool(self.forwarding_address)

    @property
    def mailbox_size_display(self):
        size = self.mailbox_size or 0
        for unit in ['B', 'KB', 'MB', 'GB']:
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def status_display(self):
        return AccountStatus.label(self.status)

    @property
    def zimbra_status_display(self):
        return ZimbraStatus.__dict__.get(self.zimbra_status, self.zimbra_status)

    def __repr__(self):
        return f"<Account {self.email}>"


class PurgeQueue(Base):
    __tablename__ = 'purge_queue'

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    account = relationship('Account', back_populates='purge_entries')
    eligible_date = Column(Date, index=True, nullable=False)
    status = Column(String(20), default=PurgeQueueStatus.WAITING)
    approved_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    approved_by = relationship('User', foreign_keys=[approved_by_id])
    approved_at = Column(DateTime, nullable=True)
    skipped_reason = Column(String(255), default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def status_display(self):
        return PurgeQueueStatus.label(self.status)

    def __repr__(self):
        return f"<PurgeQueue {self.account_id} - {self.status}>"
