"""User entity representing citizen, admin, and super admin identity."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    CITIZEN = "citizen"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


@dataclass
class User:
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole = UserRole.CITIZEN
    id: Optional[int] = None
    is_verified: bool = True
    permissions: Optional[str] = "[]"
    created_at: Optional[datetime] = None

    def is_admin(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN
