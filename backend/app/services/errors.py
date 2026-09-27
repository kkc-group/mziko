class ServiceError(Exception):
    """Base class; the API layer maps subclasses to HTTP statuses."""


class NotFound(ServiceError):
    pass


class InvalidStep(ServiceError):
    pass


class SessionFinished(ServiceError):
    pass
