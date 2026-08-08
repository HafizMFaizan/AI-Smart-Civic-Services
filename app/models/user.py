"""User entity representing citizen and admin identity."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    CITIZEN = "citizen"
    ADMIN = "admin"


@dataclass
class User:
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole = UserRole.CITIZEN
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
