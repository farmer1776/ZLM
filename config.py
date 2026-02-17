import os
from core.encryption import load_config

BASE_DIR = os.path.dirname(__file__)

# Load encrypted config
try:
    _conf = load_config()
except FileNotFoundError:
    _conf = {}

_django = _conf.get('django', {})
_zimbra = _conf.get('zimbra', {})
_redis = _conf.get('redis', {})
_database = _conf.get('database', {})


class Settings:
    APP_NAME = 'Zimbra Lifecycle Manager'
    APP_VERSION = '1.0.0'

    SECRET_KEY = _django.get('secret_key', 'insecure-dev-key-change-in-production')
    DEBUG = _django.get('debug', 'true').lower() in ('true', '1', 'yes')
    ALLOWED_HOSTS = [h.strip() for h in _django.get('allowed_hosts', 'localhost,127.0.0.1').split(',')]

    # Database
    DB_HOST = _database.get('host', 'localhost')
    DB_PORT = int(_database.get('port', '3306'))
    DB_NAME = _database.get('name', 'zimbra_lifecycle')
    DB_USER = _database.get('user', 'zlm')
    DB_PASSWORD = _database.get('password', '')
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

    # Zimbra
    ZIMBRA_ADMIN_URL = _zimbra.get('admin_url', 'https://zimbra.example.com:7071/service/admin/soap')
    ZIMBRA_ADMIN_USER = _zimbra.get('admin_user', 'admin@example.com')
    ZIMBRA_ADMIN_PASSWORD = _zimbra.get('admin_password', '')

    # Auth
    LOGIN_URL = '/auth/login/'

    # Paths
    UPLOAD_DIR = os.path.join(BASE_DIR, 'data', 'uploads')
    EXPORT_DIR = os.path.join(BASE_DIR, 'data', 'exports')
    LOG_DIR = os.path.join(BASE_DIR, 'data', 'logs')

    # Pagination
    ACCOUNTS_PER_PAGE = 50
    AUDIT_LOGS_PER_PAGE = 100

    # Sync
    ZIMBRA_SYNC_BATCH_SIZE = 500
    PURGE_DELAY_DAYS = 60

    # Rate Limiting
    RATE_LIMIT_LOGIN_ATTEMPTS = 5
    RATE_LIMIT_LOGIN_WINDOW = 300  # seconds


settings = Settings()
