class ZimbraError(Exception):
    """Base exception for Zimbra operations."""
    pass


class ZimbraAuthError(ZimbraError):
    """Authentication failure."""
    pass


class ZimbraNotFoundError(ZimbraError):
    """Account or resource not found."""
    pass


class ZimbraConnectionError(ZimbraError):
    """Network or connection failure."""
    pass


class ZimbraAPIError(ZimbraError):
    """Generic Zimbra API error."""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
