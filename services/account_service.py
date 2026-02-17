import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from apps.zimbra_client.client import ZimbraAdminClient
from apps.zimbra_client.exceptions import ZimbraError
from config import settings
from models.account import Account, AccountStatus, PurgeQueue, PurgeQueueStatus
from models.audit import AuditAction, AuditLog

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    AccountStatus.ACTIVE: [AccountStatus.LOCKED, AccountStatus.CLOSED],
    AccountStatus.LOCKED: [AccountStatus.ACTIVE, AccountStatus.CLOSED],
    AccountStatus.CLOSED: [AccountStatus.ACTIVE],
    AccountStatus.PENDING_PURGE: [AccountStatus.ACTIVE],
    AccountStatus.PURGED: [],
}

ZIMBRA_STATUS_ACTIONS = {
    AccountStatus.ACTIVE: 'active',
    AccountStatus.LOCKED: 'locked',
    AccountStatus.CLOSED: 'closed',
}


class AccountService:
    """Central business logic for account lifecycle management."""

    def __init__(self, db: Session, zimbra_client=None):
        self.db = db
        self.zimbra = zimbra_client or ZimbraAdminClient()

    def change_status(self, account, new_status, user=None, reason='', sync_to_zimbra=True):
        """
        Change account status with full lifecycle rule enforcement.
        Returns (success, message) tuple.
        """
        old_status = account.status

        if new_status == old_status:
            return False, f"Account is already {new_status}"

        if new_status not in VALID_TRANSITIONS.get(old_status, []):
            return False, (
                f"Cannot transition from {old_status} to {new_status}. "
                f"Valid transitions: {', '.join(VALID_TRANSITIONS.get(old_status, []))}"
            )

        if account.status == AccountStatus.PURGED:
            return False, "Cannot change status of a purged account"

        now = datetime.utcnow()

        # Sync to Zimbra if needed
        if sync_to_zimbra and new_status in ZIMBRA_STATUS_ACTIONS:
            try:
                self.zimbra.set_account_status(
                    account.zimbra_id,
                    ZIMBRA_STATUS_ACTIONS[new_status],
                )
            except ZimbraError as e:
                logger.error("Zimbra status change failed for %s: %s", account.email, e)
                return False, f"Zimbra API error: {e}"

        # Apply status
        account.status = new_status
        account.status_changed_at = now
        account.status_changed_by_id = user.id if user else None

        # Handle closing
        if new_status == AccountStatus.CLOSED:
            account.closed_at = now
            delay = settings.PURGE_DELAY_DAYS
            account.purge_eligible_date = (now + timedelta(days=delay)).date()
            purge_entry = PurgeQueue(
                account_id=account.id,
                eligible_date=account.purge_eligible_date,
            )
            self.db.add(purge_entry)

        # Handle reactivation - clear purge fields
        if new_status == AccountStatus.ACTIVE:
            account.closed_at = None
            account.purge_eligible_date = None
            # Cancel pending purge entries
            self.db.query(PurgeQueue).filter(
                PurgeQueue.account_id == account.id,
                PurgeQueue.status.in_([PurgeQueueStatus.WAITING, PurgeQueueStatus.APPROVED]),
            ).update({PurgeQueue.status: PurgeQueueStatus.CANCELLED}, synchronize_session='fetch')

        # Update zimbra_status mirror
        if new_status in ZIMBRA_STATUS_ACTIONS:
            account.zimbra_status = ZIMBRA_STATUS_ACTIONS[new_status]

        self.db.flush()

        # Audit log
        audit = AuditLog(
            user_id=user.id if user else None,
            action=AuditAction.STATUS_CHANGE,
            target_type='account',
            target_id=str(account.id),
        )
        audit.details = {
            'email': account.email,
            'old_status': old_status,
            'new_status': new_status,
            'reason': reason,
        }
        self.db.add(audit)
        self.db.commit()

        logger.info(
            "Account %s status changed: %s -> %s by %s",
            account.email, old_status, new_status,
            user.username if user else 'system',
        )

        return True, f"Status changed from {old_status} to {new_status}"

    def process_purge_queue(self, dry_run=False):
        """Process accounts eligible for purge."""
        today = datetime.utcnow().date()
        queue_entries = (
            self.db.query(PurgeQueue)
            .filter(
                PurgeQueue.status == PurgeQueueStatus.WAITING,
                PurgeQueue.eligible_date <= today,
            )
            .all()
        )

        results = {
            'processed': 0,
            'purged': 0,
            'skipped': 0,
            'errors': 0,
            'details': [],
        }

        for entry in queue_entries:
            account = self.db.query(Account).filter(Account.id == entry.account_id).first()
            if not account:
                continue
            results['processed'] += 1

            # Skip protected accounts
            if account.is_protected:
                entry.status = PurgeQueueStatus.SKIPPED
                entry.skipped_reason = f"Protected: forwarding to {account.forwarding_address}"
                if not dry_run:
                    self.db.commit()
                results['skipped'] += 1
                results['details'].append({
                    'email': account.email,
                    'action': 'skipped',
                    'reason': entry.skipped_reason,
                })
                continue

            # Skip accounts that are no longer closed
            if account.status not in (AccountStatus.CLOSED, AccountStatus.PENDING_PURGE):
                entry.status = PurgeQueueStatus.CANCELLED
                if not dry_run:
                    self.db.commit()
                results['skipped'] += 1
                results['details'].append({
                    'email': account.email,
                    'action': 'skipped',
                    'reason': f"Account status is {account.status}",
                })
                continue

            if dry_run:
                results['purged'] += 1
                results['details'].append({
                    'email': account.email,
                    'action': 'would_purge',
                })
                continue

            # Execute purge
            try:
                self.zimbra.delete_account(account.zimbra_id)
                account.status = AccountStatus.PURGED
                account.purged_at = datetime.utcnow()
                entry.status = PurgeQueueStatus.EXECUTED
                self.db.commit()
                results['purged'] += 1
                results['details'].append({
                    'email': account.email,
                    'action': 'purged',
                })

                audit = AuditLog(
                    action=AuditAction.PURGE,
                    target_type='account',
                    target_id=str(account.id),
                )
                audit.details = {'email': account.email}
                self.db.add(audit)
                self.db.commit()

            except ZimbraError as e:
                logger.error("Purge failed for %s: %s", account.email, e)
                results['errors'] += 1
                results['details'].append({
                    'email': account.email,
                    'action': 'error',
                    'reason': str(e),
                })

        return results
