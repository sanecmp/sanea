"""Application exception hierarchy."""


class SaneaException(Exception):
    """Base class for expected sanea failures."""


class ConfigurationError(SaneaException):
    """Raised when runtime configuration is invalid."""


class RuntimeSetupError(SaneaException):
    """Raised when the application runtime cannot be prepared."""


class ServerError(SaneaException):
    """Raised when the embedded HTTP servers cannot run."""


class PkiError(ServerError):
    """Raised when the local public-key infrastructure is unusable."""


class LimitsTemplateError(SaneaException):
    """Raised when a limits snapshot operation is not allowed."""


class ComputerConfigError(SaneaException):
    """Raised when a materialized computer configuration is invalid."""


class ClientSyncError(SaneaException):
    """Base class for expected client synchronization failures."""


class ClientAccessError(ClientSyncError):
    """Raised when a computer is not allowed to synchronize."""


class ClientRequestError(ClientSyncError):
    """Raised when a synchronization request conflicts with server state."""


class ClientPayloadTooLargeError(ClientRequestError):
    """Raised when a client payload exceeds its protocol limit."""


class EventSequenceConflictError(ClientRequestError):
    """Raised when a received event sequence was already used."""
