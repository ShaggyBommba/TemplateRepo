from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Authenticated caller accepted by the application boundary."""

    subject: str
    username: str | None
    roles: frozenset[str]

    def has(self, role: str) -> bool:
        return role in self.roles
