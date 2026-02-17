import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import typer

app = typer.Typer(name='zlm', help='Zimbra Lifecycle Manager CLI')


@app.command('sync')
def sync_accounts(
    dry_run: bool = typer.Option(False, '--dry-run', help='Preview changes without applying'),
    domain: str = typer.Option('', '--domain', help='Sync only this domain'),
):
    """Synchronize accounts from Zimbra."""
    from database import SessionLocal
    from services.sync_service import sync_accounts as do_sync

    db = SessionLocal()
    try:
        typer.echo(f"Starting sync{' (dry run)' if dry_run else ''}...")
        if domain:
            typer.echo(f"Filtering domain: {domain}")

        results = do_sync(db, dry_run=dry_run, domain=domain)

        typer.echo(f"\nSync complete:")
        typer.echo(f"  Total:     {results['total']}")
        typer.echo(f"  Created:   {results['created']}")
        typer.echo(f"  Updated:   {results['updated']}")
        typer.echo(f"  Unchanged: {results['unchanged']}")
        typer.echo(f"  Errors:    {results['errors']}")

        if results['error_details']:
            typer.echo("\nErrors:")
            for err in results['error_details'][:20]:
                typer.echo(f"  - {err.get('account', '?')}: {err.get('error', '?')}")
    finally:
        db.close()


@app.command('purge')
def process_purge(
    dry_run: bool = typer.Option(False, '--dry-run', help='Preview without purging'),
):
    """Process the purge queue."""
    from database import SessionLocal
    from services.account_service import AccountService

    db = SessionLocal()
    try:
        typer.echo(f"Processing purge queue{' (dry run)' if dry_run else ''}...")

        service = AccountService(db)
        results = service.process_purge_queue(dry_run=dry_run)

        typer.echo(f"\nPurge complete:")
        typer.echo(f"  Processed: {results['processed']}")
        typer.echo(f"  Purged:    {results['purged']}")
        typer.echo(f"  Skipped:   {results['skipped']}")
        typer.echo(f"  Errors:    {results['errors']}")

        if results['details']:
            typer.echo("\nDetails:")
            for d in results['details']:
                typer.echo(f"  - {d.get('email', '?')}: {d.get('action', '?')}"
                           + (f" ({d.get('reason', '')})" if d.get('reason') else ''))
    finally:
        db.close()


@app.command('create-user')
def create_user(
    username: str = typer.Argument(..., help='Username for the new user'),
):
    """Create a new admin user."""
    import getpass
    from database import SessionLocal
    from models.user import User

    password = getpass.getpass('Password: ')
    confirm = getpass.getpass('Confirm password: ')

    if password != confirm:
        typer.echo('Error: Passwords do not match.', err=True)
        raise typer.Exit(1)

    if len(password) < 8:
        typer.echo('Error: Password must be at least 8 characters.', err=True)
        raise typer.Exit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            typer.echo(f'Error: User "{username}" already exists.', err=True)
            raise typer.Exit(1)

        user = User(username=username)
        user.set_password(password)
        db.add(user)
        db.commit()
        typer.echo(f'User "{username}" created successfully.')
    finally:
        db.close()


@app.command('list-users')
def list_users():
    """List all users."""
    from database import SessionLocal
    from models.user import User

    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.username).all()
        if not users:
            typer.echo('No users found.')
            return
        for u in users:
            status = 'active' if u.is_active else 'inactive'
            typer.echo(f"  {u.username} ({status}) - created: {u.created_at}")
    finally:
        db.close()


@app.command('generate-key')
def generate_key():
    """Generate a new encryption key."""
    from core.encryption import KEY_PATH, generate_key as gen

    if os.path.exists(KEY_PATH):
        typer.echo(f'Error: Key already exists at {KEY_PATH}', err=True)
        typer.echo('Delete it first if you want to regenerate.', err=True)
        raise typer.Exit(1)

    gen()
    typer.echo(f'Encryption key generated at {KEY_PATH}')


@app.command('encrypt-config')
def encrypt_config():
    """Encrypt sensitive values in app.conf."""
    from core.encryption import CONF_PATH, encrypt_value, is_encrypted, load_key
    import configparser

    key = load_key()
    config = configparser.ConfigParser()
    config.read(CONF_PATH)

    SENSITIVE_KEYS = ['secret_key', 'admin_password', 'password']
    encrypted_count = 0

    for section in config.sections():
        for k, v in config.items(section):
            if k in SENSITIVE_KEYS and v and not is_encrypted(v):
                config.set(section, k, encrypt_value(v, key))
                encrypted_count += 1
                typer.echo(f"  Encrypted [{section}] {k}")

    if encrypted_count:
        with open(CONF_PATH, 'w') as f:
            config.write(f)
        typer.echo(f"\n{encrypted_count} value(s) encrypted.")
    else:
        typer.echo("No values needed encryption.")


if __name__ == '__main__':
    app()
