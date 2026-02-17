from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from passlib.hash import bcrypt

from .base import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    def set_password(self, raw_password):
        self.password_hash = bcrypt.hash(raw_password)

    def check_password(self, raw_password):
        return bcrypt.verify(raw_password, self.password_hash)

    def __repr__(self):
        return f"<User {self.username}>"
