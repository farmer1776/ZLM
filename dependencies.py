from typing import Generator, Optional

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import SessionLocal
from models.user import User


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, auto-closing on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Get current user from session, or None if not logged in."""
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    """Require login; redirect to login page if not authenticated."""
    user = get_current_user(request, db)
    if user is None:
        raise _LoginRequired(request.url.path)
    return user


class _LoginRequired(Exception):
    """Raised when login is required."""
    def __init__(self, next_url: str = '/'):
        self.next_url = next_url


# Flash message helpers using session
def add_flash(request: Request, message: str, category: str = 'info'):
    """Add a flash message to the session."""
    if '_messages' not in request.session:
        request.session['_messages'] = []
    request.session['_messages'].append({'message': message, 'category': category})


def get_flashed_messages(request: Request) -> list:
    """Pop and return all flash messages from the session."""
    messages = request.session.pop('_messages', [])
    return messages
