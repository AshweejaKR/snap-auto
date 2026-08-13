class SnapAutoError(Exception):
    """Base exception for all snap_auto errors."""


class LoginFailedError(SnapAutoError):
    """Raised when login fails (bad credentials, unexpected page, 2FA, etc.)."""


class SessionExpiredError(SnapAutoError):
    """Raised when a previously saved session is no longer authenticated."""


class SelectorNotFoundError(SnapAutoError):
    """Raised when an expected UI element can't be located, likely selector drift."""


class RateLimitedError(SnapAutoError):
    """Raised when Snapchat throttles or blocks automated activity."""


class UserNotFoundError(SnapAutoError):
    """Raised when a friend/user can't be resolved by name or index."""
