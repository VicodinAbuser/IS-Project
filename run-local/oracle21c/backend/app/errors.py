"""Business-rule errors raised by app/services. main.py turns them into HTTP responses."""


class BusinessError(Exception):
    """A business rule said no, e.g. not enough stock (409) or not allowed (403)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def not_found(what: str) -> BusinessError:
    return BusinessError(404, f"{what} not found")


def conflict(message: str) -> BusinessError:
    return BusinessError(409, message)


def invalid(message: str) -> BusinessError:
    return BusinessError(422, message)


def forbidden(message: str = "You don't have permission to do this") -> BusinessError:
    return BusinessError(403, message)
