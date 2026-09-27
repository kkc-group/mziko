from datetime import datetime


class ServiceError(Exception):
    """Base class; the API layer maps subclasses to HTTP statuses."""


class NotFound(ServiceError):
    pass


class InvalidStep(ServiceError):
    pass


class SessionFinished(ServiceError):
    pass


class LessonLocked(ServiceError):
    """The lesson exists but may not be played today (see services.lessons)."""


class WrongCode(ServiceError):
    """Login code did not match; `attempts_left` before the address is locked."""

    def __init__(self, attempts_left: int) -> None:
        super().__init__("wrong code")
        self.attempts_left = attempts_left


class LoginLocked(ServiceError):
    """Too many failed logins from this address; try again after `locked_until`."""

    def __init__(self, locked_until: datetime) -> None:
        super().__init__("login locked")
        self.locked_until = locked_until
