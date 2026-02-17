import configparser
import os

from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
KEY_PATH = os.path.join(BASE_DIR, 'conf', 'encryption.key')
CONF_PATH = os.path.join(BASE_DIR, 'conf', 'app.conf')


def generate_key():
    """Generate a new Fernet key and save it."""
    key = Fernet.generate_key()
    with open(KEY_PATH, 'wb') as f:
        f.write(key)
    os.chmod(KEY_PATH, 0o600)
    return key


def load_key():
    """Load the Fernet key from disk."""
    if not os.path.exists(KEY_PATH):
        raise FileNotFoundError(
            f"Encryption key not found at {KEY_PATH}. "
            "Run 'python -m cli.main key generate' first."
        )
    with open(KEY_PATH, 'rb') as f:
        return f.read().strip()


def encrypt_value(value, key=None):
    """Encrypt a string value."""
    if key is None:
        key = load_key()
    f = Fernet(key)
    return f.encrypt(value.encode()).decode()


def decrypt_value(value, key=None):
    """Decrypt an encrypted string value."""
    if key is None:
        key = load_key()
    f = Fernet(key)
    return f.decrypt(value.encode()).decode()


def is_encrypted(value):
    """Check if a value looks like a Fernet token."""
    return value.startswith('gAAAAA')


def load_config():
    """Load and decrypt the application config file."""
    config = configparser.ConfigParser()

    if not os.path.exists(CONF_PATH):
        raise FileNotFoundError(
            f"Config file not found at {CONF_PATH}. "
            f"Copy {CONF_PATH}.example to {CONF_PATH} and configure it."
        )

    config.read(CONF_PATH)

    key = None
    if os.path.exists(KEY_PATH):
        key = load_key()

    decrypted = {}
    for section in config.sections():
        decrypted[section] = {}
        for k, v in config.items(section):
            if key and is_encrypted(v):
                decrypted[section][k] = decrypt_value(v, key)
            else:
                decrypted[section][k] = v

    return decrypted
