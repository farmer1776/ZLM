import csv
import io
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models.account import Account
from models.audit import AuditAction, AuditLog
from models.bulk_ops import BulkOperation, BulkOperationStatus, BulkOperationType
from services.account_service import AccountService

logger = logging.getLogger(__name__)


def parse_csv(file_content):
    """Parse CSV content and return list of email addresses."""
    reader = csv.reader(io.StringIO(file_content))
    emails = []
    errors = []

    for row_num, row in enumerate(reader, 1):
        if not row:
            continue
        # Skip header row
        if row_num == 1 and row[0].lower().strip() in ('email', 'email_address', 'account'):
            continue
        email = row[0].strip().lower()
        if not email:
            continue
        if '@' not in email:
            errors.append(f"Row {row_num}: Invalid email '{email}'")
            continue
        emails.append(email)

    return emails, errors


def validate_emails(db: Session, emails, operation_type):
    """Validate that emails exist and operation is valid for their status."""
    found = []
    not_found = []

    accounts = db.query(Account).filter(Account.email.in_(emails)).all()
    account_map = {a.email: a for a in accounts}

    for email in emails:
        if email in account_map:
            found.append(account_map[email])
        else:
            not_found.append(email)

    return found, not_found


def execute_bulk_operation(db: Session, bulk_op, user):
    """Execute a bulk operation against all target accounts."""
    bulk_op.status = BulkOperationStatus.PROCESSING
    db.commit()

    status_map = {
        BulkOperationType.LOCK: 'locked',
        BulkOperationType.CLOSE: 'closed',
        BulkOperationType.REACTIVATE: 'active',
    }
    new_status = status_map.get(bulk_op.operation_type)

    if not new_status:
        bulk_op.status = BulkOperationStatus.FAILED
        bulk_op.results = [{'error': f'Unknown operation type: {bulk_op.operation_type}'}]
        db.commit()
        return

    service = AccountService(db)
    results = []

    # Re-read the emails from the stored results (preview data)
    emails = [r['email'] for r in bulk_op.results if 'email' in r]
    accounts = db.query(Account).filter(Account.email.in_(emails)).all()

    for account in accounts:
        success, message = service.change_status(
            account=account,
            new_status=new_status,
            user=user,
            reason=f"Bulk operation #{bulk_op.id}",
        )
        bulk_op.processed_count += 1
        if success:
            results.append({'email': account.email, 'status': 'success', 'message': message})
        else:
            bulk_op.error_count += 1
            results.append({'email': account.email, 'status': 'error', 'message': message})

    bulk_op.results = results
    bulk_op.status = BulkOperationStatus.COMPLETED
    bulk_op.completed_at = datetime.utcnow()
    db.commit()

    audit = AuditLog(
        user_id=user.id,
        action=AuditAction.BULK_OP,
        target_type='bulk_operation',
        target_id=str(bulk_op.id),
    )
    audit.details = {
        'operation_type': bulk_op.operation_type,
        'total': bulk_op.total_count,
        'processed': bulk_op.processed_count,
        'errors': bulk_op.error_count,
    }
    db.add(audit)
    db.commit()

    logger.info(
        "Bulk operation #%d completed: %d processed, %d errors",
        bulk_op.id, bulk_op.processed_count, bulk_op.error_count,
    )
