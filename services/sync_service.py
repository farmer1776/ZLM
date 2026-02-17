import hashlib
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from apps.zimbra_client.client import ZimbraAdminClient
from apps.zimbra_client.constants import STATUS_MAP_FROM_ZIMBRA
from config import settings
from models.account import Account
from models.audit import AuditAction, AuditLog
from models.sync import SyncHistory, SyncStatus

logger = logging.getLogger(__name__)


def compute_sync_hash(data):
    """Compute MD5 hash of relevant account fields for change detection."""
    fields = '|'.join([
        data.get('name', ''),
        data.get('attrs', {}).get('displayName', ''),
        data.get('attrs', {}).get('zimbraAccountStatus', ''),
        data.get('attrs', {}).get('zimbraMailForwardingAddress', ''),
        data.get('attrs', {}).get('zimbraPrefMailForwardingAddress', ''),
        data.get('attrs', {}).get('zimbraMailQuota', ''),
        data.get('attrs', {}).get('zimbraLastLogonTimestamp', ''),
    ])
    return hashlib.md5(fields.encode()).hexdigest()


def parse_zimbra_timestamp(ts):
    """Parse Zimbra timestamp format (e.g., '20240101120000Z' or '20240101120000.123Z')."""
    if not ts:
        return None
    try:
        clean = ts.split('.')[0]
        if not clean.endswith('Z'):
            clean += 'Z'
        if len(clean) == 15:
            return datetime.strptime(clean, '%Y%m%d%H%M%SZ')
        return None
    except (ValueError, TypeError):
        return None


def sync_accounts(db: Session, dry_run=False, domain=''):
    """
    Synchronize accounts from Zimbra to local database.
    Uses sync_hash for change detection to minimize DB writes.
    """
    sync_record = None
    if not dry_run:
        sync_record = SyncHistory()
        db.add(sync_record)
        db.commit()

    client = ZimbraAdminClient()
    batch_size = settings.ZIMBRA_SYNC_BATCH_SIZE

    created = 0
    updated = 0
    unchanged = 0
    errors = 0
    error_details = []
    total = 0

    try:
        for zimbra_account in client.get_all_accounts(domain=domain, batch_size=batch_size):
            total += 1
            try:
                result = _sync_single_account(db, zimbra_account, dry_run=dry_run, client=client)
                if result == 'created':
                    created += 1
                elif result == 'updated':
                    updated += 1
                else:
                    unchanged += 1
            except Exception as e:
                errors += 1
                error_details.append({
                    'account': zimbra_account.get('name', 'unknown'),
                    'error': str(e),
                })
                logger.error("Sync error for %s: %s", zimbra_account.get('name'), e)

    except Exception as e:
        logger.error("Sync failed: %s", e)
        if sync_record:
            sync_record.status = SyncStatus.FAILED
            sync_record.error_details = [{'error': str(e)}]
            sync_record.completed_at = datetime.utcnow()
            db.commit()
        raise

    if sync_record:
        sync_record.status = SyncStatus.COMPLETED
        sync_record.completed_at = datetime.utcnow()
        sync_record.total_accounts = total
        sync_record.created_count = created
        sync_record.updated_count = updated
        sync_record.unchanged_count = unchanged
        sync_record.error_count = errors
        sync_record.error_details = error_details
        db.commit()

        audit = AuditLog(
            action=AuditAction.SYNC,
            target_type='sync',
            target_id=str(sync_record.id),
        )
        audit.details = {
            'total': total,
            'created': created,
            'updated': updated,
            'unchanged': unchanged,
            'errors': errors,
        }
        db.add(audit)
        db.commit()

    logger.info(
        "Sync complete: total=%d, created=%d, updated=%d, unchanged=%d, errors=%d",
        total, created, updated, unchanged, errors,
    )

    return {
        'total': total,
        'created': created,
        'updated': updated,
        'unchanged': unchanged,
        'errors': errors,
        'error_details': error_details,
    }


def _sync_single_account(db: Session, zimbra_data, dry_run=False, client=None):
    """Sync a single account from Zimbra data. Returns 'created', 'updated', or 'unchanged'."""
    zimbra_id = zimbra_data['id']
    email = zimbra_data['name']
    attrs = zimbra_data.get('attrs', {})

    new_hash = compute_sync_hash(zimbra_data)

    account = db.query(Account).filter(Account.zimbra_id == zimbra_id).first()

    if account:
        if account.sync_hash == new_hash:
            return 'unchanged'

        if dry_run:
            return 'updated'

        _update_account_from_zimbra(account, email, attrs, client=client)
        account.sync_hash = new_hash
        db.commit()
        return 'updated'
    else:
        if dry_run:
            return 'created'

        domain = email.split('@')[1] if '@' in email else ''
        account = Account(zimbra_id=zimbra_id, email=email, domain=domain)
        _update_account_from_zimbra(account, email, attrs, client=client)
        account.sync_hash = new_hash
        db.add(account)
        db.commit()
        return 'created'


def _update_account_from_zimbra(account, email, attrs, client=None):
    """Update account fields from Zimbra attributes."""
    account.email = email
    account.domain = email.split('@')[1] if '@' in email else ''
    account.display_name = attrs.get('displayName', '')
    account.forwarding_address = (
        attrs.get('zimbraPrefMailForwardingAddress', '')
        or attrs.get('zimbraMailForwardingAddress', '')
    )
    account.cos_name = attrs.get('zimbraCOSId', '')

    zimbra_status = attrs.get('zimbraAccountStatus', 'active')
    mapped_status = STATUS_MAP_FROM_ZIMBRA.get(zimbra_status, 'active')
    account.zimbra_status = mapped_status

    # Only update local status if it hasn't been locally managed
    if not account.status_changed_by_id:
        account.status = mapped_status

    # Fetch actual mailbox size via GetMailboxRequest
    if client and account.zimbra_id:
        try:
            account.mailbox_size = client.get_mailbox_size(account.zimbra_id)
        except Exception:
            pass

    last_login = parse_zimbra_timestamp(attrs.get('zimbraLastLogonTimestamp', ''))
    if last_login:
        account.last_login_at = last_login
