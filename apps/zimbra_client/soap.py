import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from .constants import ZIMBRA_ADMIN_NS, ZIMBRA_SOAP_NS

SOAP_ENV_NS = 'http://www.w3.org/2003/05/soap-envelope'

_ENVELOPE_OPEN = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
)
_ENVELOPE_CLOSE = '</soap:Envelope>'
_HEADER_NO_AUTH = '<soap:Header><context xmlns="urn:zimbra"/></soap:Header>'
_HEADER_AUTH = (
    '<soap:Header><context xmlns="urn:zimbra">'
    '<authToken>{token}</authToken><nosession/>'
    '</context></soap:Header>'
)


def _wrap(body_xml, auth_token=None):
    """Wrap body XML in a SOAP envelope."""
    if auth_token:
        header = _HEADER_AUTH.format(token=escape(auth_token))
    else:
        header = _HEADER_NO_AUTH
    return f'{_ENVELOPE_OPEN}{header}<soap:Body>{body_xml}</soap:Body>{_ENVELOPE_CLOSE}'


def build_auth_request(username, password):
    """Build AuthRequest SOAP envelope."""
    body = (
        f'<AuthRequest xmlns="urn:zimbraAdmin">'
        f'<name>{escape(username)}</name>'
        f'<password>{escape(password)}</password>'
        f'</AuthRequest>'
    )
    return _wrap(body)


def build_search_directory_request(auth_token, query='', domain='', limit=500, offset=0,
                                   attrs=None):
    """Build SearchDirectoryRequest SOAP envelope."""
    parts = [
        f'<SearchDirectoryRequest xmlns="urn:zimbraAdmin"'
        f' limit="{limit}" offset="{offset}"'
        f' types="accounts" sortBy="name" sortAscending="1"'
    ]
    if attrs:
        parts.append(f' attrs="{escape(",".join(attrs))}"')
    if domain:
        parts.append(f' domain="{escape(domain)}"')
    parts.append('>')
    if query:
        parts.append(f'<query>{escape(query)}</query>')
    parts.append('</SearchDirectoryRequest>')
    return _wrap(''.join(parts), auth_token)


def build_get_account_request(auth_token, account_id, by='id'):
    """Build GetAccountRequest SOAP envelope."""
    body = (
        f'<GetAccountRequest xmlns="urn:zimbraAdmin">'
        f'<account by="{escape(by)}">{escape(account_id)}</account>'
        f'</GetAccountRequest>'
    )
    return _wrap(body, auth_token)


def build_modify_account_request(auth_token, zimbra_id, attrs):
    """Build ModifyAccountRequest SOAP envelope."""
    attr_xml = ''.join(
        f'<a n="{escape(name)}">{escape(str(value))}</a>'
        for name, value in attrs.items()
    )
    body = (
        f'<ModifyAccountRequest xmlns="urn:zimbraAdmin">'
        f'<id>{escape(zimbra_id)}</id>'
        f'{attr_xml}'
        f'</ModifyAccountRequest>'
    )
    return _wrap(body, auth_token)


def build_delete_account_request(auth_token, zimbra_id):
    """Build DeleteAccountRequest SOAP envelope."""
    body = (
        f'<DeleteAccountRequest xmlns="urn:zimbraAdmin">'
        f'<id>{escape(zimbra_id)}</id>'
        f'</DeleteAccountRequest>'
    )
    return _wrap(body, auth_token)


def build_get_mailbox_request(auth_token, zimbra_id):
    """Build GetMailboxRequest SOAP envelope."""
    body = f'<GetMailboxRequest xmlns="urn:zimbraAdmin"><mbox id="{escape(zimbra_id)}"/></GetMailboxRequest>'
    return _wrap(body, auth_token)


def build_get_all_cos_request(auth_token):
    """Build GetAllCosRequest SOAP envelope."""
    body = '<GetAllCosRequest xmlns="urn:zimbraAdmin"/>'
    return _wrap(body, auth_token)


def parse_response(xml_text):
    """Parse SOAP response, returning the body content element."""
    root = ET.fromstring(xml_text)
    body = root.find(f'{{{SOAP_ENV_NS}}}Body')
    if body is None:
        raise ValueError("No SOAP Body found in response")

    fault = body.find(f'{{{SOAP_ENV_NS}}}Fault')
    if fault is not None:
        reason = fault.find(f'{{{SOAP_ENV_NS}}}Reason')
        if reason is not None:
            text = reason.find(f'{{{SOAP_ENV_NS}}}Text')
            if text is not None:
                return {'fault': True, 'message': text.text}
        detail = fault.find(f'{{{SOAP_ENV_NS}}}Detail')
        if detail is not None:
            error = detail.find(f'{{{ZIMBRA_SOAP_NS}}}Error')
            if error is not None:
                code_el = error.find(f'{{{ZIMBRA_SOAP_NS}}}Code')
                msg = error.find(f'{{{ZIMBRA_SOAP_NS}}}Trace')
                return {
                    'fault': True,
                    'message': msg.text if msg is not None else 'Unknown error',
                    'code': code_el.text if code_el is not None else None,
                }
        return {'fault': True, 'message': 'Unknown SOAP fault'}

    return {'fault': False, 'body': body}


def parse_account_element(account_el):
    """Parse an <account> element into a dict."""
    data = {
        'id': account_el.get('id', ''),
        'name': account_el.get('name', ''),
        'attrs': {},
    }
    for a in account_el.findall(f'{{{ZIMBRA_ADMIN_NS}}}a'):
        name = a.get('n', '')
        data['attrs'][name] = a.text or ''
    if not data['attrs']:
        for a in account_el.findall('a'):
            name = a.get('n', '')
            data['attrs'][name] = a.text or ''
    return data


def parse_auth_response(xml_text):
    """Parse AuthResponse to extract auth token."""
    result = parse_response(xml_text)
    if result.get('fault'):
        return result
    body = result['body']
    auth_resp = body.find(f'{{{ZIMBRA_ADMIN_NS}}}AuthResponse')
    if auth_resp is None:
        return {'fault': True, 'message': 'No AuthResponse found'}
    # authToken may be namespaced or not depending on Zimbra version
    token_el = auth_resp.find(f'{{{ZIMBRA_ADMIN_NS}}}authToken')
    if token_el is None:
        token_el = auth_resp.find('authToken')
    if token_el is None:
        return {'fault': True, 'message': 'No authToken found'}
    return {'fault': False, 'auth_token': token_el.text}


def parse_search_response(xml_text):
    """Parse SearchDirectoryResponse to extract accounts."""
    result = parse_response(xml_text)
    if result.get('fault'):
        return result
    body = result['body']
    search_resp = body.find(f'{{{ZIMBRA_ADMIN_NS}}}SearchDirectoryResponse')
    if search_resp is None:
        return {'fault': True, 'message': 'No SearchDirectoryResponse found'}

    accounts = []
    # Account elements may be namespaced or not
    for acct_el in search_resp.findall(f'{{{ZIMBRA_ADMIN_NS}}}account'):
        accounts.append(parse_account_element(acct_el))
    if not accounts:
        for acct_el in search_resp.findall('account'):
            accounts.append(parse_account_element(acct_el))

    more = search_resp.get('more', 'false').lower() == 'true'
    total = int(search_resp.get('searchTotal', len(accounts)))

    return {'fault': False, 'accounts': accounts, 'more': more, 'total': total}
