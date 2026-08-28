from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessContext:
    is_authenticated: bool
    can_write: bool
    email: str | None = None


class ReadOnlyError(PermissionError):
    """Raised when a demo user attempts to mutate data."""


def require_write(access: AccessContext) -> None:
    if not access.can_write:
        raise ReadOnlyError("Le mode démonstration est en lecture seule.")
