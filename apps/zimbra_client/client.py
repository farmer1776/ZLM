import logging
import threading

import requests

from .constants import STATUS_MAP_TO_ZIMBRA, ZIMBRA_ACCOUNT_ATTRS
from .exceptions import (
    ZimbraAPIError,
    ZimbraAuthError,
    ZimbraConnectionError,
    ZimbraNotFoundError,
)
from .soap import (
    build_auth_request,
    build_delete_account_request,
    build_get_account_request,
    build_get_mailbox_request,
    build_modify_account_request,
    build_search_directory_request,
    parse_account_element,
    parse_auth_response,
    parse_response,
    parse_search_response,
)

logger = logging.getLogger(__name__)


class ZimbraAdminClient:
    """Thread-safe Zimbra Admin SOAP API client."""

    def __init__(self, url=None, username=None, password=None):
        from config import settings
        self.url = url or settings.ZIMBRA_ADMIN_URL
        self.username = username or settings.ZIMBRA_ADMIN_USER
        self.password = password or settings.ZIMBRA_ADMIN_PASSWORD
        self._auth_token = None
        self._lock = threading.RLock()
        self._session = requests.Session()
        self._session.verify = True
        self._session.headers.update({'Content-Type': 'application/soap+xml; charset=UTF-8'})

    def _send(self, xml_payload):
        """Send a SOAP request and return raw response text."""
        try:
            response = self._session.post(self.url, data=xml_payload, timeout=60)
            response.raise_for_status()
            return response.text
        except requests.exceptions.ConnectionError as e:
            raise ZimbraConnectionError(f"Cannot connect to Zimbra: {e}") from e
        except requests.exceptions.Timeout as e:
            raise ZimbraConnectionError(f"Zimbra request timed out: {e}") from e
        except requests.exceptions.HTTPError as e:
            raise ZimbraAPIError(f"HTTP error: {e}") from e

    def authenticate(self):
        """Authenticate and store the auth token."""
        xml = build_auth_request(self.username, self.password)
        response_text = self._send(xml)
        result = parse_auth_response(response_text)
        if result.get('fault'):
            raise ZimbraAuthError(result['message'])
        with self._lock:
            self._auth_token = result['auth_token']
        logger.info("Authenticated with Zimbra as %s", self.username)

    @property
    def auth_token(self):
        with self._lock:
            if not self._auth_token:
                self.authenticate()
            return self._auth_token

    def search_accounts(self, query='', domain='', limit=500, offset=0):
        """Search directory for accounts with pagination."""
        xml = build_search_directory_request(
            self.auth_token, query=query, domain=domain,
            limit=limit, offset=offset, attrs=ZIMBRA_ACCOUNT_ATTRS,
        )
        response_text = self._send(xml)
        result = parse_search_response(response_text)
        if result.get('fault'):
            raise ZimbraAPIError(result['message'])
        return result

    def get_all_accounts(self, domain='', batch_size=500):
        """Iterate over all accounts using pagination."""
        offset = 0
        while True:
            result = self.search_accounts(domain=domain, limit=batch_size, offset=offset)
            accounts = result['accounts']
            yield from accounts
            if not result['more']:
                break
            offset += batch_size

    def get_account(self, account_id, by='id'):
        """Get a single account by ID or name."""
        xml = build_get_account_request(self.auth_token, account_id, by=by)
        response_text = self._send(xml)
        result = parse_response(response_text)
        if result.get('fault'):
            msg = result['message']
            if 'no such account' in msg.lower():
                raise ZimbraNotFoundError(f"Account not found: {account_id}")
            raise ZimbraAPIError(msg)
        body = result['body']
        acct_el = body.find('.//{urn:zimbraAdmin}GetAccountResponse/account')
        if acct_el is None:
            for el in body.iter():
                if el.tag.endswith('GetAccountResponse'):
                    for child in el:
                        if child.tag == 'account' or child.tag.endswith('}account'):
                            return parse_account_element(child)
            raise ZimbraNotFoundError(f"Account not found: {account_id}")
        return parse_account_element(acct_el)

    def modify_account(self, zimbra_id, attrs):
        """Modify account attributes."""
        xml = build_modify_account_request(self.auth_token, zimbra_id, attrs)
        response_text = self._send(xml)
        result = parse_response(response_text)
        if result.get('fault'):
            raise ZimbraAPIError(result['message'])
        logger.info("Modified account %s: %s", zimbra_id, list(attrs.keys()))

    def set_account_status(self, zimbra_id, status):
        """Change account status in Zimbra."""
        zimbra_status = STATUS_MAP_TO_ZIMBRA.get(status)
        if not zimbra_status:
            raise ValueError(f"Cannot map status '{status}' to Zimbra status")
        self.modify_account(zimbra_id, {'zimbraAccountStatus': zimbra_status})

    def get_mailbox_size(self, zimbra_id):
        """Get mailbox size in bytes via GetMailboxRequest."""
        xml = build_get_mailbox_request(self.auth_token, zimbra_id)
        response_text = self._send(xml)
        result = parse_response(response_text)
        if result.get('fault'):
            return 0
        body = result['body']
        for el in body.iter():
            if el.tag.endswith('}mbox') or el.tag == 'mbox':
                return int(el.get('s', 0))
        return 0

    def delete_account(self, zimbra_id):
        """Permanently delete an account."""
        xml = build_delete_account_request(self.auth_token, zimbra_id)
        response_text = self._send(xml)
        result = parse_response(response_text)
        if result.get('fault'):
            raise ZimbraAPIError(result['message'])
        logger.info("Deleted account %s", zimbra_id)

    def test_connection(self):
        """Test connection by authenticating."""
        self.authenticate()
        return True
