from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from dependencies import add_flash, get_db, require_login
from models.bulk_ops import BulkOperation, BulkOperationStatus, BulkOperationType
from models.user import User
from services.bulk_ops_service import execute_bulk_operation, parse_csv, validate_emails

router = APIRouter(prefix='/bulk', tags=['bulk_ops'])


@router.get('/')
def bulk_upload_page(request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)):
    recent_ops = (
        db.query(BulkOperation)
        .filter(BulkOperation.user_id == user.id)
        .order_by(BulkOperation.created_at.desc())
        .limit(10)
        .all()
    )
    return request.state.templates.TemplateResponse('bulk_ops/upload.html', {
        'request': request,
        'user': user,
        'recent_ops': recent_ops,
        'operation_type_choices': BulkOperationType.choices,
    })


# POST handler for bulk upload (needs async form data for file upload)
from starlette.routing import Route


async def _bulk_upload_post_handler(request: Request):
    from database import SessionLocal
    db = SessionLocal()
    try:
        user_id = request.session.get('user_id')
        if not user_id:
            return RedirectResponse(url='/auth/login/', status_code=302)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return RedirectResponse(url='/auth/login/', status_code=302)

        form = await request.form()
        operation_type = form.get('operation_type', '')
        csv_file = form.get('csv_file')

        if not csv_file or not hasattr(csv_file, 'read'):
            add_flash(request, 'Please upload a CSV file.', 'danger')
            return RedirectResponse(url='/bulk/', status_code=302)

        # Validate file
        filename = csv_file.filename or 'upload.csv'
        if not filename.endswith('.csv'):
            add_flash(request, 'Only CSV files are accepted.', 'danger')
            return RedirectResponse(url='/bulk/', status_code=302)

        content = (await csv_file.read()).decode('utf-8', errors='replace')

        # Check file size (5MB limit)
        if len(content) > 5 * 1024 * 1024:
            add_flash(request, 'File size must be under 5MB.', 'danger')
            return RedirectResponse(url='/bulk/', status_code=302)

        emails, parse_errors = parse_csv(content)

        if parse_errors:
            for err in parse_errors[:10]:
                add_flash(request, err, 'warning')

        if not emails:
            add_flash(request, 'No valid email addresses found in CSV.', 'danger')
            return RedirectResponse(url='/bulk/', status_code=302)

        found_accounts, not_found = validate_emails(db, emails, operation_type)

        # Create the bulk operation with preview data
        bulk_op = BulkOperation(
            user_id=user.id,
            operation_type=operation_type,
            filename=filename,
            total_count=len(emails),
        )
        bulk_op.results = [{'email': a.email, 'status': a.status} for a in found_accounts]
        db.add(bulk_op)
        db.commit()
        db.refresh(bulk_op)

        templates = request.state.templates
        return templates.TemplateResponse('bulk_ops/upload.html', {
            'request': request,
            'user': user,
            'preview': True,
            'bulk_op': bulk_op,
            'found_accounts': found_accounts,
            'not_found': not_found,
            'operation_type': operation_type,
            'operation_type_choices': BulkOperationType.choices,
        })
    finally:
        db.close()


@router.get('/{pk}/execute/')
def bulk_execute(request: Request, pk: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    bulk_op = db.query(BulkOperation).filter(
        BulkOperation.id == pk, BulkOperation.user_id == user.id
    ).first()

    if not bulk_op:
        add_flash(request, 'Operation not found.', 'danger')
        return RedirectResponse(url='/bulk/', status_code=302)

    if bulk_op.status != BulkOperationStatus.PENDING:
        add_flash(request, 'This operation has already been executed.', 'danger')
        return RedirectResponse(url=f'/bulk/{pk}/results/', status_code=302)

    execute_bulk_operation(db, bulk_op, user)
    add_flash(
        request,
        f'Bulk operation completed: {bulk_op.processed_count} processed, {bulk_op.error_count} errors.',
        'success',
    )
    return RedirectResponse(url=f'/bulk/{pk}/results/', status_code=302)


@router.get('/{pk}/results/')
def bulk_results(request: Request, pk: int, user: User = Depends(require_login), db: Session = Depends(get_db)):
    bulk_op = db.query(BulkOperation).filter(
        BulkOperation.id == pk, BulkOperation.user_id == user.id
    ).first()

    if not bulk_op:
        add_flash(request, 'Operation not found.', 'danger')
        return RedirectResponse(url='/bulk/', status_code=302)

    return request.state.templates.TemplateResponse('bulk_ops/results.html', {
        'request': request,
        'user': user,
        'bulk_op': bulk_op,
    })
