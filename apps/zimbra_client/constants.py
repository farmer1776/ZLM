ZIMBRA_ADMIN_NS = 'urn:zimbraAdmin'
ZIMBRA_ACCOUNT_NS = 'urn:zimbraAccount'
ZIMBRA_SOAP_NS = 'urn:zimbra'

ZIMBRA_ACCOUNT_ATTRS = [
    'zimbraAccountStatus',
    'displayName',
    'zimbraMailForwardingAddress',
    'zimbraPrefMailForwardingAddress',
    'zimbraMailQuota',
    'zimbraLastLogonTimestamp',
    'zimbraCOSId',
    'zimbraMailHost',
    'mail',
]

STATUS_MAP_TO_ZIMBRA = {
    'active': 'active',
    'locked': 'locked',
    'closed': 'closed',
}

STATUS_MAP_FROM_ZIMBRA = {
    'active': 'active',
    'locked': 'locked',
    'closed': 'closed',
    'lockout': 'locked',
    'maintenance': 'locked',
}
